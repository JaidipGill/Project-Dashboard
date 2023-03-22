import requests
from http import HTTPStatus
import pandas as pd

VERTO_API = 'https://www.vertocloud.com/eahsn/api/'


def get_entity(entity, describe=False):
    r = requests.get(VERTO_API + entity, auth=('API-USER', 'API-KEY'))
    sc = r.status_code
    if HTTPStatus.OK != sc:
        raise RuntimeError(f"Unsuccessful request, HTTP status code: {sc}")
    data = r.json()
    context = data['@odata.context']
    df_entity = pd.DataFrame(data['value'])
    if describe: describe_entity(entity, df_entity)
    return context, df_entity


def describe_entity(name, data):
    print(f'Columns of "{name}"')
    for col in data.columns:
        print(f"\t{col}")


(ctx_project, df_project) = get_entity('Project')
print(df_project[['ProjectID', 'ProjectCode','ProjectName']])


## get another data table
#(ctx_ags, df_ags) = get_entity('ProjectExtended', True)

## join the tables
#joined = pd.merge(df_project, df_customer, on='ProjectID', how='outer', suffixes=('_prj', '_note'))

## Filter tables
#is_pr = joined['ProjectCode']=='PR000098'
#print(joined[is_pr][['ProjectID', 'ProjectCode','ProjectName',]])
