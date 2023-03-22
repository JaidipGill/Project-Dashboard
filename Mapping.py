import fire, os, yaml, geopandas, subprocess, warnings
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio
import numpy as np
import geofeather as gf

#Ignoring warning outputs
pd.options.mode.chained_assignment = None  # default='warn'
warnings.filterwarnings('ignore', message='.*crs will be set for this GeoDataFrame.*')

#Defines the command needed to run this code, an example command could be: python mapping.py generate mkdocs/docs
def generate(outdir='mkdocs/docs', output_mode='external', path_to_data='data', path_to_config='config_mkdocs.yml', path_to_site='mkdocs'):
    
    '''
    This 'generate' function will output an organisational view, project view and overall view.\n
    outdir - Specifies output directory (recommended to choose docs folder in mkdocs folder to auto update site)\n
    output_mode - Choose either external or internal views.\n
    path_to_data - Folder containing input csv and shape files.\n
    path_to_config - yaml file containing configuration.\n
    path_to_site - Folder containing mkdocs documents.
    '''

    #Creates out directory if it doesn't exist already
    if not os.path.exists(outdir):
        os.makedirs(outdir, exist_ok=True)

    #Opens yml config file, use this file to make minor stylistic edits
    with open(path_to_config, "r") as file:
        config = yaml.safe_load(file)
    projects_config=config['project_view']
    organisations_config=config['organisation_view']
    overall_config=config['overall_view']

    #Checking if implementation data files have been updated since mkdocs last generated
    def check_report_modification():
        recent=0
        if not os.listdir(f"{path_to_data}/{config['files']['individual_reports']}"):
            return False
        
        for filename in os.listdir(f"{path_to_data}/{config['files']['individual_reports']}"):
            filemod = os.path.getmtime(f"{path_to_data}/{config['files']['individual_reports']}/{filename}")
            if filemod > recent:
                recent = filemod
        if not os.path.exists(f'{outdir}/{overall_config["filename"]}'):
            return True
        elif recent > os.path.getmtime(f'{outdir}/{overall_config["filename"]}'):
            return True
        else:
            return False

    #Generating combined_report.csv if required
    if check_report_modification():
        df = pd.DataFrame(list())
        for filename in os.listdir(f"{path_to_data}/{config['files']['individual_reports']}"):
            filepath = f"{path_to_data}/{config['files']['individual_reports']}/{filename}"
            filename = filename.replace('.csv', '')
            myVars = locals()
            myVars[filename] = pd.read_csv(filepath)
            myVars[filename]['Portfolio'] = filename
            myVars[filename]['ProjectName'] = filename + ' - ' + myVars[filename]['ProjectName'] 
            df = pd.concat([df, myVars[filename]])
        df.drop_duplicates(subset=None, inplace=True)
        df.to_csv(f"{path_to_data}/{config['files']['implementation_report']}", index=False)
        print(f"{config['files']['implementation_report']} has been updated")

    #Checks whether the .geojson shapefiles have been updated
    def check_shapefile_modification(filename):
        geojson = os.path.getmtime(f"{path_to_data}/{config['files']['geojson_files'][filename]}")
        if os.path.exists(f"{path_to_data}/{config['files']['feather_files'][filename]}"):
            feather = os.path.getmtime(f"{path_to_data}/{config['files']['feather_files'][filename]}")
            if geojson > feather:
                return True
            else:
                return False
        else:
            return True
    
    #Converts updated .geojson files to .feather files if required
    for file in ['lsoas','stps','local_authorities']:
        if check_shapefile_modification(file):
            df = geopandas.read_file(f"{path_to_data}/{config['files']['geojson_files'][file]}")
            df["wkb"] = df.geometry.apply(lambda g: g.wkb)
            df = df.drop(columns=["geometry"])
            df.to_feather(f"{path_to_data}/{config['files']['feather_files'][file]}")
            print(f'{path_to_data}/{config["files"]["geojson_files"][file]} was updated')
        else:
            print(f'{path_to_data}/{config["files"]["geojson_files"][file]} is up-to-date')

    #Importing datasets
    implementation_report=pd.read_csv(f"{path_to_data}/{config['files']['implementation_report']}")
    organisations=pd.read_csv(f"{path_to_data}/{config['files']['organisations']}")


    #Finding number of projects
    frequencies = implementation_report['Name'].value_counts().rename_axis('Name').reset_index(name='Project Number')
    organisations = organisations.merge(frequencies, left_on='Name', right_on='Name', how='outer')
    organisations.replace({'STP: ':'ICS: '},regex=True,inplace=True)
    implementation_report.replace({'STP: ':'ICS: '},regex=True,inplace=True)
    organisations['Project Number'] = organisations['Project Number'].fillna(0)
    implementation_report[['Interest','Stage']]=implementation_report[['Interest','Stage']].fillna('Not Available')

    #Generating dataframes for STPs/ICSs + cleaning data
    ics_locations=pd.read_csv(f"{path_to_data}/{config['files']['ics_locations']}")
    stps = gf.from_geofeather(f"{path_to_data}/{config['files']['feather_files']['stps']}")
    stps.replace({'Cambridgeshire and Peterborough': 'ICS: Cambridge and Peterborough',
                'Norfolk and Waveney Health and Care Partnership': 'ICS: Norfolk and Waveney',
                'Suffolk and North East Essex':'ICS: Suffolk and North East Essex',
                'Bedfordshire, Luton and Milton Keynes': 'ICS: BLMK',
                'Hertfordshire and West Essex': 'ICS: Herts and West Essex',
                #'Mid and South Essex': 'ICS: Mid and South Essex'
                },inplace=True)
    stps=stps[stps['STP21NM'].isin(ics_locations['Name'])]
    stps_pd = pd.DataFrame(stps.drop(columns='geometry'))
    stps_pd.rename(columns={"STP21NM": "Name"},inplace=True)
    stps_pd = stps_pd.merge(organisations[['Name','Project Number']], left_on='Name', right_on='Name')
    stps_pd = stps_pd.merge(ics_locations[['Name','Longitude','Latitude']], left_on='Name', right_on='Name')
    stps_pd=stps_pd.merge(pd.get_dummies(stps_pd['Name']),left_index=True, right_index=True)


    #Filtering by region
    def region_filter(region):
        filtered_data=implementation_report.query(f'Name.str.contains("{region}")')
        return filtered_data['ProjectName'].to_list()

    #Adding column for project list with line break formatting
    names=organisations['Name'].to_list()
    projects={}
    for i in names:
        projects[f"{i}"]='\n'.join((region_filter(f"{i}")))
    projects=pd.DataFrame.from_dict(projects,orient='index',columns=['Projects'])
    projects['Projects']=projects['Projects'].str.replace('\n','<br>',regex=True)
    organisations=organisations.merge(projects,left_on='Name',right_index=True)
    stps_pd=stps_pd.merge(projects,left_on='Name',right_index=True)

    #Filtering by project
    implementation_report['Stage Number']=(implementation_report['Stage'].str.extract('(\d+)')).fillna(0)
    implementation_report['Stage Number'] = pd.to_numeric(implementation_report['Stage Number'])
    #Creates a stage 3.1, Decision No
    implementation_report['Project View Stage Number'] = np.where(implementation_report['Stage Number'] > 3, implementation_report['Stage Number'] + 1, implementation_report['Stage Number'])
    implementation_report['Project View Stage Number'] = implementation_report.apply(lambda x: 4 if ' Yes - ' in x['Interest'] and x['Project View Stage Number'] == 3 else x['Project View Stage Number'], axis=1)

    #Find which organisations are involved in each project
    project_names = sorted(set(implementation_report['ProjectName']))
    project_dfs={}
    for i in project_names:
        project_dfs[i]=organisations.query(f'Projects.str.contains("{i}",regex = False)')
        project_dfs[i]=project_dfs[i].merge(implementation_report.query(f'ProjectName.str.contains("{i}",regex = False)'),left_on='Name',right_on='Name')

    #Creating LSOA data
    ethnicity=pd.read_csv(f"{path_to_data}/{config['files']['ethnicity']}")
    imd=pd.read_csv(f"{path_to_data}/{config['files']['imds']}")
    age=pd.read_csv(f"{path_to_data}/{config['files']['age']}")
    age['population'] = pd.Series(dtype=int)
    age['population'] = np.where(True, (age['Age 65 and over'] + age['Age 0 to 24'] + age['Age 25 to 49'] + age['Age 50 to 64']), age['population'])
    age['Age 65 and over'] = np.where(True, round(100*(age['Age 65 and over']/age['population']), 1), age['Age 65 and over'])

    #Cleaning lsoa shapefile
    lsoa = gf.from_geofeather(f"{path_to_data}/{config['files']['feather_files']['lsoas']}") 
    lsoa_pd = pd.DataFrame(lsoa.drop(columns='geometry'))
    lsoa_pd= lsoa_pd.merge(ethnicity,left_on='LSOA11CD',right_on='LSOA_CODE')
    lsoa_pd= lsoa_pd.merge(age,left_on='LSOA11CD',right_on='LSOA_CODE')
    lsoa_pd= lsoa_pd.merge(imd,left_on='LSOA11CD',right_on='lsoa11cd')
    lsoa_pd.rename(columns={"IMDDec0":"Index of multiple deprivation decile"},inplace=True)

    #Generating dataframes for LAs
    population_regional=pd.read_csv(f"{path_to_data}/{config['files']['population_regional']}")
    imd_regional=pd.read_csv(f"{path_to_data}/{config['files']['imd_regional']}")
    ethnicity_regional=pd.read_csv(f"{path_to_data}/{config['files']['ethnicity_regional']}")

    #Cleaning LA shapefile
    authority = gf.from_geofeather(f"{path_to_data}/{config['files']['feather_files']['local_authorities']}")
    authority_pd = pd.DataFrame(authority.drop(columns='geometry'))
    authority_pd= (authority_pd.merge(imd_regional,left_on='LAD21CD',right_on='Local Authority District code (2019)')).drop(columns='Local Authority District code (2019)')
    authority_pd= (authority_pd.merge(population_regional,left_on='LAD21CD',right_on='Area code')).drop(columns='Area code')
    authority_pd= (authority_pd.merge(ethnicity_regional,left_on='LAD21CD',right_on='Area code')).drop(columns='Area code')
    authority_pd=authority_pd[authority_pd['LAD21CD'].str.startswith('E09')==False]
    areas_to_drop=['South Oxfordshire','Oadby and Wigston','Harborough','Melton','Rutland']
    authority_pd=authority_pd[~authority_pd['LAD21NM'].str.contains('|'.join(areas_to_drop))]
    authority_customdata=authority_pd[['LAD21NM','Income deprivation rate quintile','BAME %',r'% of all persons 65+']]

    #Function to create a colour scale based on 
    def colorbar_discretize(colour,colour_indices):
        n_cat=len(colour_indices)
        colour_list=[]
        colourscale=[]
        n=0
        for i in range(0,n_cat):
                colour_list.append(colour[colour_indices[i]])
                colourscale.append([i/n_cat,colour_list[i]])
                colourscale.append([(i+1)/n_cat,colour_list[i]])
        return(colourscale)

    def select_button(button_list):
        button_list.insert(0,dict(label = 'Select...',
            method = 'update',
            args = [{'visible': False},
                    {'title': f'Please Select',
                    'showlegend':True}],
            ))
        return button_list

    def generate_organisation_view():

        organisations_bar=go.Figure()
                
        #Creates organisation dataframe, including differentiating between Stage 3 Yes & No outcomes
        organisations_dfs=[]
        implementation_report['Project Ended?']=np.where((implementation_report['Stage Number']==3) & (implementation_report['Interest'].str.contains('Decision No')),'Yes','No')
        for idx, organisation in enumerate(sorted(set(implementation_report['Name']))):
            organisations_dfs.append(implementation_report[implementation_report['Name']==organisation])
            organisations_dfs[idx]['Color']=np.where(organisations_dfs[idx]['Project Ended?']=='Yes',organisations_config['decision_no_color'],organisations_config['other_project_color'])
            organisations_dfs[idx]['WhyImportant'].fillna('',inplace=True)
            organisations_dfs[idx]['WhyImportant']=organisations_dfs[idx]['WhyImportant'].str.findall('.' * 50).map('<br>'.join)

        #Adds a button in the dropdown for each organisation
        buttons_orgs=[]
        visibility_orgs=[False]*len(organisations_dfs)
        annotation=[
                {   
                    "text": "Please select an organisation",
                    "xref": "paper",
                    "yref": "paper",
                    "showarrow": False,
                    "font": {
                        "size": 28
                    }
                }
            ]
        for idx, organisation in enumerate(organisations_dfs):
                organisations_bar.add_bar(
                        x=organisation['Stage Number'],
                        y=organisation['ProjectName'],
                        visible=False,
                        showlegend=False,
                        orientation='h',
                        marker_color=organisation['Color'],
                        customdata=organisation,
                        hovertemplate="<br>".join([
                                "<b>%{customdata[3]}</b><extra></extra>"]),
                )
                #Creating dropdown, so it updates chart and title
                visibility_orgs[idx]=True
                buttons_orgs.append(dict(label = organisation['Name'].iloc[0],
                    method = 'update',
                    args = [{'visible': visibility_orgs},
                            {'title': f'{organisations_config["title_organisation"]} {organisation["Name"].iloc[0]}{organisations_config["subheading"]}',
                            'showlegend':True,
                            'xaxis':{
                                    'tickmode':'array',
                                    'tickvals':[0,1,2,3,4,5,6,7],
                                    'ticktext':['0 - No Information','1 - Knowledge', '2 - Interest', '3 - Decision', '4 - Implementation', 
                                                '5 - Adoption', '6 - Spread<br><sup>(PSC Only)</sup>','7 - Sustained<br><sup>(PSC Only)</sup>'],
                                    'range':[0,7],
                                    'title':{'text':'Stage Number'}
                                    },
                            "annotations": []
                            }
                            ])
                )
                visibility_orgs=[False]*len(organisations_dfs)
        buttons_orgs.insert(0,dict(label = 'Select...',
            method = 'update',
            args = [{'visible': False},
                    {'title': f'Please Select',
                    'showlegend':True,
                    "annotations": annotation}],
            ))
        #Creating bar chart
        organisations_bar.update_yaxes(
            title_text='Project',
        )
        organisations_bar.update_layout(
            title=dict(
                yanchor="top", xanchor="left",
                y=0.97, x=0.015,
                text=f'{organisations_config["title_default"]} {organisations_config["subheading"]}'),
            margin=dict(
                t=80, b=10,
                r=15, l=15,),
            updatemenus=[
                {"buttons": buttons_orgs,'x':organisations_config["button_pos_x"],'y':organisations_config["button_pos_y"],}],
            annotations = annotation
        )
        visibility_orgs=[False]*len(organisations_dfs)

        #Outputting pioorgs.html file
        pio.write_html(organisations_bar, file=f'{outdir}/{organisations_config["filename"]}', auto_open=False)
        print(f'{organisations_config["filename"]} was created')

    def generate_project_view():

        project_fig = go.Figure()

        #Creating scatter traces for each project
        for i in project_names:
            project_fig.add_scattermapbox(lat = project_dfs[i]['Latitude']
                            ,lon = project_dfs[i]['Longitude']
                            ,hovertext = project_dfs[i]['Name']
                            ,customdata = project_dfs[i]
                            ,hovertemplate="<br>".join([
                                "<b>%{customdata[0]}</b><extra></extra>",
                                "<br>%{customdata[8]}",
                                ])
                            ,visible=False
                            ,marker_size=15
                            ,marker_colorscale=colorbar_discretize([getattr(px.colors.sequential,projects_config['colorbar'])[i] for i in [1,2,3,4,5,6,7,8]],
                                                                    [0,1,2,3,4,5,6,7])
                            ,marker_color= project_dfs[i]['Project View Stage Number']
                            ,marker_cmin=0
                            ,marker_cmax=7
                            ,marker_showscale=True
                            ,marker_colorbar_title_text='Stage Number'
                            ,marker_colorbar_ticktext=[' 0 - No Information',' 1 - Knowledge', ' 2 - Interest', ' 3 - Decision: No',
                                                        '3.1 - Decision:Yes', ' 4 - Implementation', ' 5 - Adoption', '<br> 6 - Spread<br><sup>(Only PSC)</sup>']
                            ,marker_colorbar_tickvals=[0,1,2,3,4,5,6,7]
                            ,name=i
                            ,showlegend=False
                            ,opacity=projects_config['opacity']
                            )

        #Adding dropdown buttons for each project
        visibility=[False]*len(project_names)
        buttons_projects=[]
        for idx, name in enumerate(project_names):
            visibility[idx]=True
            buttons_projects.append(dict(label = name,
            method = 'update',
            args = [{'visible': visibility},
                    {'title': f'{projects_config["title_project"]} {name}{projects_config["subheading"]}',
                    'showlegend':True}],
            ))
            visibility=[False]*len(project_names)
        select_button(buttons_projects)
        
        #Matching each project to a portfolio
        project_names_df = pd.DataFrame(project_names)
        portfolios=set(implementation_report['Portfolio'])
        visibility_portfolios={}
        for portfolio in portfolios:
                visibility_portfolios[portfolio]=project_names_df[0].str.startswith(portfolio)

        #Adding dropdown buttons for each portfolio
        buttons_programmes=[]
        for portfolio in portfolios:
                buttons_programmes.append(dict(label = portfolio,
                        method = 'update',
                        args = [{'visible': visibility_portfolios[portfolio]},
                        {'title': f'{projects_config["title_portfolio"]} {portfolio} {projects_config["subheading"]}'}]
                        ))
        select_button(buttons_programmes)

        #Creating project view map
        project_fig.update_layout(
            title=dict(
                text=f'{projects_config["title_default"]}{projects_config["subheading"]}',
                yanchor="top", xanchor="left",
                y=0.98, x=0.001),
            legend=dict(
                yanchor="top", xanchor="left",
                y=0.98, x=0.01,),
            mapbox=dict(
                style="open-street-map",
                zoom=projects_config['zoom'],
                center={"lat": 52.1951, "lon": 0.1313}),
            updatemenus=[
                {"buttons": buttons_projects,'x':projects_config["project_button"]["pos_x"],'y':projects_config["project_button"]["pos_y"]},
                {"buttons": buttons_programmes,'x': projects_config["portfolio_button"]["pos_x"],'y':projects_config["portfolio_button"]["pos_y"]}],
            margin=dict(
                t=80, b=10,
                r=10, l=10,),
            hoverdistance=10,
            )
        
        pio.write_html(project_fig, file=f'{outdir}/{projects_config["filename"]}', auto_open=False)
        print(f'{projects_config["filename"]} was created')

    def generate_overall_view():

        fig = go.Figure()

        buttons_1=[]
        visibility=[False]*7+[False]*len(stps_pd['Name'])+[True]
        df_customdata=lsoa_pd[['lsoa11nm','BAME %','Age 65 and over','Index of multiple deprivation decile']]

        #Adding choropleth map for each shapefile
        for idx, descriptor in enumerate(['LA: Income deprivation rate quintile','LA: BAME %',r'LA: % of all persons 65+','LSOA: Index of multiple deprivation decile','LSOA: BAME %','LSOA: Age 65 and over','ICSs']):
            if 'LA:' in descriptor:
                fig.add_trace(
                go.Choroplethmapbox(
                                geojson=authority.__geo_interface__,
                                customdata=authority_customdata,
                                locations=authority_pd['LAD21NM'],
                                featureidkey="properties.LAD21NM",
                                z=authority_pd[descriptor.replace('LA: ','')],
                                name = descriptor,
                                visible=False))
            elif 'LSOA:' in descriptor:
                fig.add_trace(
                go.Choroplethmapbox(
                                geojson=lsoa.__geo_interface__,
                                customdata=df_customdata,
                                locations=lsoa_pd.index,
                                z=lsoa_pd[descriptor.replace('LSOA: ','')],
                                name = descriptor,
                                visible=False))
            elif 'ICSs' in descriptor:
                fig.add_trace(
                go.Choroplethmapbox(
                                geojson=stps.__geo_interface__,
                                customdata=stps_pd,
                                locations=stps.index,
                                z=stps_pd['Project Number'],
                                name = descriptor))
            visibility[idx]=True
            #Adding each choropleth map to a dropdown
            buttons_1.append(dict(label = f'{descriptor}',
                                    method = 'update',
                                    args = [{'visible': visibility,'showscale':visibility},
                                            {'title': f'{descriptor}{overall_config["subheading"]}',
                                            'showlegend':True,
                                            }],
                                    ))
            visibility=[False]*7+[False]*len(stps_pd['Name'])+[True]
        select_button(buttons_1)

        #Adding choropleth maps for each ICS then adding them to a dropdown
        buttons_ics=[]
        for idx, name in enumerate(stps_pd['Name']):
            fig.add_trace(
                go.Choroplethmapbox(
                                geojson=stps.__geo_interface__,
                                customdata=stps_pd,
                                locations=stps.index,
                                z=stps_pd[name],
                                name = name,
                                visible=False
                ))
            visibility[7+idx]=True
            buttons_ics.append(dict(label = name,
                        method = 'update',
                        args = [{'visible': visibility,'showscale':False,},
                        {'title': f'{name}{overall_config["subheading"]}',}
                        ]
                        )
                    )
            visibility=[False]*7+[False]*len(stps_pd['Name'])+[True]
        select_button(buttons_ics)
        
        #Calculates the maximum number of projects an ICS has
        max_ics = 0
        for item in stps_pd['Project Number']:
            if int(item) > max_ics:
                 max_ics = int(item)
        if max_ics > 8:
            max_ics = 8

        #For each choropleth map, update the colours, colorbars, titles
        fig.update_traces(selector=({'name':'ICSs'}),
                        marker_opacity=0.5,
                        hovertemplate="<br>".join([
                                "<b>%{customdata[2]}</b><extra></extra>",
                                "Project Number: %{customdata[10]}<br>",
                                "%{customdata[18]}",
                                ]),
                        colorscale=colorbar_discretize(getattr(px.colors.sequential,overall_config['colorbars']['ics']),list(range(1,max_ics+2))),
                        zmin=0,
                        zmax=max_ics+1,
                        colorbar_tickvals=list(range(0,max_ics+1)),
                        colorbar_title='No. of Projects in ICS',
                        colorbar_tickmode = 'array',
                        visible=False
                        )     

        fig.update_traces(selector=({'name':'LSOA: BAME %'}),
                        marker_opacity=0.3,
                        hovertemplate="<br>".join([
                                "<b>%{customdata[0]}</b><extra></extra>",
                                "<br>% BAME: %{customdata[1]}",
                                ]),
                        colorscale=overall_config['colorbars']['lsoa_bame'],
                        colorbar_title='BAME %'
                        )

        fig.update_traces(selector=({'name':'LSOA: Age 65 and over'}),
                        marker_opacity=0.3,
                        hovertemplate="<br>".join([
                                "<b>%{customdata[0]}</b><extra></extra>",
                                "<br>Population over 65: %{customdata[2]}",
                                ]),
                        colorscale=overall_config['colorbars']['lsoa_age'],
                        colorbar_title=r'% Over 65'
                        )

        fig.update_traces(selector=({'name':'LSOA: Index of multiple deprivation decile'}),
                        marker_opacity=0.3,
                        hovertemplate="<br>".join([
                                "<b>%{customdata[0]}</b><extra></extra>",
                                "<br>IMD Decile: %{customdata[3]}",
                                ]),
                        colorscale=colorbar_discretize(getattr(px.colors.sequential,overall_config['colorbars']['lsoa_imd'])+['rgb(255,255,255)'],[0,1,2,3,4,5,6,7,8,9]),
                        colorbar_tickvals=[1,2,3,4,5,6,7,8,9,10],
                        colorbar_ticktext=[' 1 - Most Deprived','2', '3',
                                            '4', '5', '6','7','8','9','10 - Least Deprived'],
                        colorbar_tickmode = 'array',
                        colorbar_title='IMD Decile'
                        )

        #formatting each view
        fig.update_traces(selector=({'name':'LA: Income deprivation rate quintile'}),
                        marker_opacity=0.5,
                        hovertemplate="<br>".join([
                                "<b>%{customdata[0]}</b><extra></extra>",
                                "<br>IncDep Quintile: %{customdata[1]}",
                                ]),
                        colorscale=colorbar_discretize(getattr(px.colors.sequential,overall_config['colorbars']['la_imd']),[0,2,4,6,8]),
                        colorbar_tickvals=[1,2,3,4,5],
                        colorbar_ticktext=[' 1 - Most Deprived','2', '3',
                                            '4', '5 - Least Deprived'],
                        colorbar_tickmode = 'array',
                        colorbar_title='IncDep Quintile'
                        )

        fig.update_traces(selector=({'name':'LA: BAME %'}),
                        marker_opacity=0.5,
                        hovertemplate="<br>".join([
                                "<b>%{customdata[0]}</b><extra></extra>",
                                "<br>% BAME: %{customdata[2]}",
                                ]),
                        colorscale=getattr(px.colors.sequential,overall_config['colorbars']['la_bame']),
                        colorbar_title='BAME %'
                        )

        fig.update_traces(selector=({'name':r'LA: % of all persons 65+'}),
                        marker_opacity=0.5,
                        hovertemplate="<br>".join([
                                "<b>%{customdata[0]}</b><extra></extra>",
                                "<br>Over 65 %: %{customdata[3]}",
                                ]),
                        colorscale=getattr(px.colors.sequential,overall_config['colorbars']['la_age']),
                        colorbar_title=r'% Over 65'
                        )

        for idx, name in enumerate(stps_pd['Name']):
            fig.update_traces(selector=({'name':f'{name}'}),
                        marker_opacity=0.3,
                        hovertemplate="<br>".join([
                                "<b>%{customdata[2]}</b><extra></extra>",
                                "Project Number: %{customdata[10]}<br>",
                                "%{customdata[18]}",
                                ]),
                        colorscale=getattr(px.colors.sequential,overall_config['colorbars']['ics_selection']),
                        )                                                 

        #Adding organisations scatter layer
        fig.add_scattermapbox(lat = organisations['Latitude']
                            ,lon = organisations['Longitude']
                            ,hovertext = organisations['Name']
                            ,customdata = organisations
                            ,hovertemplate="<br>".join([
                                "<b>%{customdata[0]}</b><extra></extra>",
                                "Project Number: %{customdata[4]}<br>",
                                "%{customdata[5]}",
                                ])
                            ,marker_color= organisations['Project Number']
                            ,marker_colorscale=colorbar_discretize(getattr(px.colors.sequential,overall_config['colorbars']['scatter']),[0,1,2,3,4,5,6,7,8,9,10])
                            ,marker_colorbar_title_text='No. of Projects (Scatter plot)'
                            ,marker_colorbar_ticktext=list(range(int(min(organisations['Project Number'])),int(max(organisations['Project Number']+1))))
                            ,marker_colorbar_tickvals=list(range(int(min(organisations['Project Number'])),int(max(organisations['Project Number']+1))))
                            ,marker_colorbar_tickmode='array'
                            ,marker_colorbar_x=0.52
                            ,marker_colorbar_y=-0.22
                            ,marker_colorbar_orientation='h'
                            ,marker_size=10
                            ,name='Organisations'
                            ,opacity=0.9
                            ,visible=False
                            ,showlegend=True
                            )
        #Styling the map
        fig.update_layout(title=dict(
                                text=f'{overall_config["title_default"]} {overall_config["subheading"]}',
                                yanchor="top", xanchor="left",
                                y=0.96, x=0.02),
                        mapbox=dict(
                            style="open-street-map",
                            zoom=6,
                            center={"lat": 52.1951, "lon": 0.1313}),
                        legend=dict(
                        yanchor="top",
                        y=0.99,
                        xanchor="left",
                        x=0.01
                        ),
                        updatemenus=[
                            {"buttons": buttons_1,'x':overall_config['heatmap_button']["pos_x"],'y':overall_config['heatmap_button']["pos_y"],'active':0},
                            {"buttons": buttons_ics,'x':overall_config['ics_button']["pos_x"],'y':overall_config['ics_button']["pos_y"]}],)
        
        #Output overall view
        pio.write_html(fig, file=f'{outdir}/{overall_config["filename"]}', auto_open=False)
        print(f'{overall_config["filename"]} was created')

    if output_mode == 'internal':
        
        generate_organisation_view()
        generate_project_view()
        generate_overall_view()

    if output_mode == 'external':

        generate_organisation_view()
        generate_project_view()
        generate_overall_view()
        
    #generate mkdocs site
    subprocess.run('mkdocs serve',cwd=path_to_site)
        

class Pipeline(object):
    def __init__(self):
        self.generate=generate

if __name__ == "__main__":
    fire.Fire(Pipeline)

    
