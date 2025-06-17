import sqlalchemy
import pandas as pd
import re

with open('db_psd.txt', 'r') as fp:
    tmp_pw = fp.read().strip()

# Find a list of all series marked excluded
# Find unique qqcs subj session from those.
# Filter by only curated qqc (bool on qqc)
# Now...go through all curated series, group by subj. Check for exclusions and no replacements.
#


db_engine = sqlalchemy.create_engine(
    f"postgresql+psycopg2://pipeline:{tmp_pw}"
    "@pnl-postgres-1.partners.org:5432/ampscz_db")

sqlquery = '''
select
  qws.id,
	qws.series_number,
	qws.series_description,
	qws.extra_series_to_be_excluded as excluded,
	qws.most_recent_series as most_recent,
	qws.qqc_id,
	qws.json_filename,
	qwq.subject_str,
	qwq.session_str
from
	mri.qqc_web_series qws
left join
	mri.qqc_web_qqc qwq on
	qws.qqc_id = qwq.id
where
	qwq.curated = true and qws.most_recent_series = true
'''
all_series_df = pd.read_sql(sqlquery, db_engine)

print('All series info')
print(all_series_df.head())

# Creates list of series ids for each subject and session pair
grouped_series = all_series_df.groupby(
    ['subject_str', 'session_str']
)['id'].apply(lambda x: list(x)).reset_index(name='id_list')
print('Grouped by subject and session. A list of all ids of series contained within.')
print(grouped_series)

excluded_series_df = all_series_df[all_series_df['excluded'] == True]

fname_mapping = {}


def is_rescan(excl_fname, curr_fname):
    if not excl_fname or excl_file_name is None:
        pass  # Need to check desc and if same desc and greater series number
    if not curr_fname or curr_fname is None:
        pass
    if excl_fname == curr_fname:
        return True

    # This regex will match filenames that are identical except for the run-X part,
    # where X can be any digit. If any other part differs, the match fails.
    regex_pattern = r'^(?P<pre>.*_run-)[0-9]+(?P<post>.*)$'

    print(type(excl_fname), type(curr_fname))
    m_excl = re.fullmatch(regex_pattern, excl_fname)
    m_curr = re.fullmatch(regex_pattern, curr_fname)
    if m_excl and m_curr:
        # Check that both strings are identical except for the run number
        return (m_excl.group("pre") == m_curr.group("pre") and
                m_excl.group("post") == m_curr.group("post") and
                m_excl.group(0) != m_curr.group(0))
    return False


# 'qqc_id' -> [(series_id, series_num), ()...]
sessions_with_excludes = dict()

# Loop through all series which are marked as excluded.
# Store the entire series they are contained in.
for row in excluded_series_df.itertuples():
    subj = row.subject_str
    ses = row.session_str
    qqc_id = row.qqc_id

    # Exclude sessions already seen with at least 1 exclusion.
    if qqc_id not in sessions_with_excludes.keys():
        # Identify list of series in this session
        ses_lst = grouped_series.loc[(grouped_series['subject_str'] == subj) &
                                     (grouped_series['session_str'] == ses), 'id_list'].iloc[0]

        # Get series number and turn into tuple (id, series number)
        ses_lst = [(s, int(all_series_df.loc[all_series_df['id'] ==
                    s, 'series_number'].iloc[0])) for s in ses_lst]

        sessions_with_excludes[qqc_id] = ses_lst  # Store

# Loop through each session that contains an exclusion
print(f'{len(sessions_with_excludes)} sessions that contain at least 1 excluded series.')
for qqc_id, series_lst in sessions_with_excludes.items():

    # Sort list of series by series_number
    print(f'List of series: {series_lst}')
    sorted_ser = sorted(series_lst, key=lambda x: x[1])
    print(f'List of sorted series: {sorted_ser}')

    # Loop through all series ascending series_number to find first excluded
    for s_id, s_num in sorted_ser:

        # If this session is not excluded, skip past.
        if s_id not in excluded_series_df['id'].values:
            continue
        else:  # Otherwise...identify the filename here.
            excl_file_name = excluded_series_df.loc[excluded_series_df['id']
                                                    == s_id, 'json_filename'].iloc[0]

            # For all excluded series only...loop through the series AFTER it to determine if a rescan of same type occurred
            # Filter series_lst to only include series with higher numbers than current
            higher_series = list(filter(lambda x: x[1] > s_num, sorted_ser))
            for s1_id, s1_num in higher_series:
                curr_file_name = all_series_df.loc[all_series_df['id']
                                                   == s1_id, 'json_filename'].iloc[0]
                print(s1_id, s1_num)
                if is_rescan(excl_file_name, curr_file_name):
                    fname_mapping[excl_file_name] = curr_file_name

                # print(qqc_id, s_num, s1_num, higher_series)


print(fname_mapping)
