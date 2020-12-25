#!/usr/bin/env python3
"""
This is a script for creating maps with reef locations
It is a modification from the CBASS84 script I used to make the figure for that paper
We will aim for it to take command inputs of the map bounding latitudes and longitudes
By default we will plot the world reefs on the map
We will also want to be able to add additional reefs to the map through some sort of csv import

# Finish documentation
# produce examples
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import argparse
# NB the pip cartopy install seems to be broken as it doesn't install the required libararies.
# The solution was to install using conda. conda install cartopy.
# I then had to downgrade shapely to 1.5.17. pip install shapely==1.5.17
from cartopy.mpl.gridliner import Gridliner
import matplotlib.ticker as mticker
import cartopy.crs as ccrs
import cartopy
from matplotlib.patches import Polygon
from datetime import datetime
from cartopy.io.shapereader import Reader
import numpy as np
import time
from matplotlib.colors import is_color_like
import re
import matplotlib as mpl

mpl.use('TKAgg')

__version__ = "v0.1.0"


class MapWthInsetFigure:
    def __init__(self):
        print(f"""
        
                         __ __  __             __  __       _             
                        / _|  \/  |           |  \/  |     | |            
          _ __ ___  ___| |_| \  / | __ _ _ __ | \  / | __ _| | _____ _ __ 
         | '__/ _ \/ _ \  _| |\/| |/ _` | '_ \| |\/| |/ _` | |/ / _ \ '__|
         | | |  __/  __/ | | |  | | (_| | |_) | |  | | (_| |   <  __/ |   
         |_|  \___|\___|_| |_|  |_|\__,_| .__/|_|  |_|\__,_|_|\_\___|_|   
                                        | | {__version__}                              
                                        |_|                               

        """)
        print("""
            reefMapMaker uses the Global Distribution of Coral Reefs data set.
            
            From https://data.unep-wcmc.org/datasets/1:
            
            This dataset shows the global distribution of coral reefs in tropical and subtropical regions.
            It is the most comprehensive global dataset of warm-water coral reefs to date, acting as a
            foundation baseline map for future, more detailed, work.
            This dataset was compiled from a number of sources by UNEP World Conservation Monitoring Centre
            (UNEP-WCMC) and the WorldFish Centre, in collaboration with WRI (World Resources Institute) and
            TNC (The Nature Conservancy). Data sources include the Millennium Coral Reef Mapping Project
            (IMaRS-USF and IRD 2005, IMaRS-USF 2005) and the World Atlas of Coral Reefs (Spalding et al. 2001).
            
            When using maps containing the reference coral reefs, please enusre you include the relevant citations
            to this UNEP-WCMC resource.
            
            From https://data.unep-wcmc.org/datasets/1:
            Citations:
            UNEP-WCMC, WorldFish Centre, WRI, TNC (2018). Global distribution of warm-water coral reefs, compiled from 
            multiple sources including the Millennium Coral Reef Mapping Project. Version 4.0. Includes contributions 
            from IMaRS-USF and IRD (2005), IMaRS-USF (2005) and Spalding et al. (2001). Cambridge (UK): UN Environment 
            World Conservation Monitoring Centre. URL: http://data.unep-wcmc.org/datasets/1\n
    
            Citations for the separate entities:
            IMaRS-USF (Institute for Marine Remote Sensing-University of South Florida) (2005). Millennium Coral Reef 
            Mapping Project. Unvalidated maps. These maps are unendorsed by IRD, but were further interpreted by UNEP 
            World Conservation Monitoring Centre. Cambridge (UK): UNEP World Conservation Monitoring Centre
            
            IMaRS-USF, IRD (Institut de Recherche pour le Developpement) (2005). Millennium Coral Reef Mapping Project. 
            Validated maps. Cambridge (UK): UNEP World Conservation Monitoring Centre
            
            Spalding MD, Ravilious C, Green EP (2001). World Atlas of Coral Reefs. Berkeley (California, USA): 
            The University of California Press. 436 pp.\n\n\n\n
        """)
        parser = argparse.ArgumentParser(
            description='A script to make maps with annotated coral reef locations',
            epilog='For support email: didillysquat@gmail.com')
        self._define_runtime_args(parser)
        self._define_config_args(parser)
        self.args = parser.parse_args()
        self.root_dir = os.getcwd()
        self.date_time = str(datetime.now()).split('.')[0].replace('-', '').replace(' ', 'T').replace(':', '')

        # User input
        # We will allow user configurations through both the command line and a config file
        # We should prioritise command line input
        # Probably the clearest and most logical way to do this will be to go parameter by parameter
        self._set_param_defaults_dict()
        if self.args.config_sheet:
            self._config_setup_with_sheet()
        else:
            self._config_setup_without_sheet()

        if self.args.site_sheet:
            self._user_site_setup()
        else:
            print('No user site sheet provided. User sites will not be plotted.')

        self.reference_reef_shape_file_path = self._find_shape_path()

        self.fig = self._setup_map_figure()

        self.large_map_ax = plt.subplot(projection=ccrs.PlateCarree(), zorder=1)
        self.large_map_ax.set_extent(extents=(
            self.config_dict['bounds'][0], self.config_dict['bounds'][1], self.config_dict['bounds'][2],
            self.config_dict['bounds'][3]))
        # Scalar for converting the user inputted coordinate radii to point format for plotting
        self.coord_to_point_scaler = self._calc_scaler()

        self._setup_fig_output_paths()

    def _setup_fig_output_paths(self):
        if not self.args.fig_out_dir:
            self.fig_out_path_svg = os.path.join(self.root_dir, f'map_out_{self.date_time}.svg')
            self.fig_out_path_png = os.path.join(self.root_dir, f'map_out_{self.date_time}.png')
        else:
            if not os.path.exists(os.path.abspath(self.args.fig_out_dir)):
                print(f'Creating {self.args.fig_out_dir}')
                os.makedirs(os.path.abspath(self.args.fig_out_dir))
            self.fig_out_path_svg = os.path.join(self.args.fig_out_dir, f'map_out_{self.date_time}.svg')
            self.fig_out_path_png = os.path.join(self.args.fig_out_dir, f'map_out_{self.date_time}.png')

    def _user_site_setup(self):
        print('Reading in site sheet')
        if self.args.site_sheet.endswith('.tsv'):
            self.site_df = pd.read_csv(self.args.site_sheet, index_col=0, sep='\t').sort_values(
                'radius_in_deg_lat', axis=0, ascending=False)
        elif self.args.site_sheet.endswith('.xlsx'):
            self.site_df = pd.read_excel(
                self.args.site_sheet, sheet_name='user_site', index_col=0
            ).sort_values('radius_in_deg_lat', axis=0, ascending=False)
        print('Checking user sites...')
        self._check_site_sheet()
        print('User site checks complete.')

    def _config_setup_without_sheet(self):
        # no config sheet provided
        # Use default dict
        self.config_dict = {}
        self._setup_config()

    def _config_setup_with_sheet(self):
        # Config sheet
        print('Checking user config...')
        if self.args.config_sheet.endswith('.tsv'):
            config_df = pd.read_csv(self.args.config_sheet, index_col=0, sep='\t')
        elif self.args.config_sheet.endswith('.xlsx'):
            config_df = pd.read_excel(self.args.config_sheet, sheet_name='user_config', index_col=0)
        else:
            raise RuntimeError("Unrecognised format for config-sheet. Please provided .xlsx or .tsv.")
        self.config_dict = {k: v for k, v in zip(config_df.index.values, config_df['value'].values)}
        self._setup_config()
        print('User config checks complete.')

    def _set_param_defaults_dict(self):
        self.param_defaults_dict = {
            'bounds': [-180, 180, -90, 90],
            'plot_sea': True,
            'sea_color': '#88b5e0',
            'plot_reference_reefs': True,
            'reference_reef_color': '#003366',
            'plot_land': True, 'land_color': 'white',
            'plot_grid_lines': True, 'lon_grid_line_pos': None,
            'lat_grid_line_pos': None, 'lon_grid_lab_pos': 'bottom',
            'lat_grid_lab_pos': 'left', 'plot_boundaries': True,
            'reference_reef_patch_type': 'polygon', 'user_site_labels': True
        }

    def _check_site_sheet(self):
        """
        Check the site_sheet input for valid inputs
        """
        for site in self.site_df.index:
            self._check_site_lat_lon(site)
            self._check_site_marker_radius(site)
            self._check_site_marker_colors(site)

    def _check_site_marker_colors(self, site):
        if not is_color_like(self.site_df.at[site, 'facecolor']):
            raise RuntimeError(
                f"facecolor {self.site_df.at[site, 'facecolor']} for site {site} is not a valid color.\n"
                f"Please check your site sheet."
            )
        if not is_color_like(self.site_df.at[site, 'edgecolor']):
            raise RuntimeError(
                f"edgecolor {self.site_df.at[site, 'edgecolor']} for site {site} is not a valid color.\n"
                f"Please check your site sheet."
            )

    def _check_site_marker_radius(self, site):
        if not pd.isnull(self.site_df.at[site, 'radius_in_deg_lat']):
            try:
                float(self.site_df.at[site, 'radius_in_deg_lat'])
            except ValueError:
                raise RuntimeError(f"Unable to convert marker radius for {site} into decimal number.\n"
                                   f"Please check your site sheet.")
        else:
            raise RuntimeError(f'No valid marker radius provided for site {site}.\n'
                               f'Please check your site sheet.')

    def _check_site_lat_lon(self, site):
        lat = self.site_df.at[site, 'latitude_deg_n']
        lon = self.site_df.at[site, 'longitude_deg_e']
        if pd.isnull(lat) or pd.isnull(lon):
            raise RuntimeError(f"invalid lat or lon format for site {site}")
        try:
            self.site_df.at[site, 'latitude_deg_n'] = float(lat)
            self.site_df.at[site, 'longitude_deg_e'] = float(lon)
        except ValueError:
            self._attempt_fix_lat_lon_format(lat, lon, site)

    def _attempt_fix_lat_lon_format(self, lat, lon, site):
        print("WARNING: Unable to convert lat or lon value for {site} to decimal degrees.")
        print("Attempting to fix the format")
        try:
            new_lat = self._attempt_lat_fix(lat, site)
            new_lon = self._attempt_lon_fix(lon)
        except Exception:
            # see if they are in proper dms format
            new_lat, new_lon = self._attempt_convert_from_dms(lat, lon, new_lat, new_lon, site)
        print(f"For {site}:\n"
              f"\tlatitude was converted from {lat} --> {new_lat}\n"
              f"\tlongitude was converted from {lon} --> {new_lon}")

    def _attempt_convert_from_dms(self, lat, lon, new_lat, new_lon, site):
        try:
            new_lat = self.dms2dec(lat)
            new_lon = self.dms2dec(lon)
        # if all this fails, convert to 999
        except Exception:
            raise RuntimeError(f'Unable to fix lat lon format for {site}')
        return new_lat, new_lon

    def _attempt_lon_fix(self, lon):
        if 'E' in lon:
            new_lon = float(lon.replace('E', '').replace(chr(176), ''))
            # lon_float should be positive
            if new_lon < 0:
                new_lon = new_lon * -1
        elif 'W' in lon:
            new_lon = float(lon.replace('W', '').replace(chr(176), ''))
            # lon_float should be negative
            if new_lon > 0:
                new_lon = new_lon * -1
        else:
            # There was not an N or S found in the lat so we should raise error
            raise RuntimeError
        return new_lon

    def _attempt_lat_fix(self, lat, site):
        if 'N' in lat:
            new_lat = float(lat.replace('N', '').replace(chr(176), ''))
            # lat_float should be positive
            if new_lat < 0:
                new_lat = new_lat * -1
        elif 'S' in lat:
            new_lat = float(lat.replace('S', '').replace(chr(176), ''))
            # lat_float should be negative
            if new_lat > 0:
                new_lat = new_lat * -1
        else:
            # There was not an N or S found in the lat so we should raise error
            raise RuntimeError(f'Unable to fix lat lon format for {site}')
        return new_lat

    @staticmethod
    def dms2dec(dms_str):
        """Return decimal representation of DMS

            dms2dec(utf8(48°53'10.18"N))
            48.8866111111F

            dms2dec(utf8(2°20'35.09"E))
            2.34330555556F

            dms2dec(utf8(48°53'10.18"S))
            -48.8866111111F

            dms2dec(utf8(2°20'35.09"W))
            -2.34330555556F

            """

        dms_str = re.sub(r'\s', '', dms_str)

        sign = -1 if re.search('[swSW]', dms_str) else 1

        numbers = [*filter(len, re.split('\D+', dms_str, maxsplit=4))]

        degree = numbers[0]
        minute = numbers[1] if len(numbers) >= 2 else '0'
        second = numbers[2] if len(numbers) >= 3 else '0'
        frac_seconds = numbers[3] if len(numbers) >= 4 else '0'

        second += "." + frac_seconds
        return sign * (int(degree) + float(minute) / 60 + float(second) / 3600)

    def _calc_scaler(self):
        """
        Users input the size of their reefs to be plotted in coordinate system radii, i.e. 0.01 deg
        We need to convert these values to point values that can then be squared to use the scatter
        plot size unit for plotting.
        The transformations required are quite mind bending so I have included some helpful links here:
        https://matplotlib.org/3.1.1/tutorials/advanced/transforms_tutorial.html
        https://stackoverflow.com/a/47403507/5516420
        https://stackoverflow.com/a/33945420/5516420

        Our approach is to use a set of data points that are 1 deg lon apart
        We convert these to display units and therefore workout what 1 deg lon is in display units (pixels)
        We then convert this pixel length to a point length with:
        points = (pixels * 72) / dpi
        This length is then the scalar and will need to be squared when supplied to the size argument of scatter
        """
        # points in data coordinates
        p1_da = (5, 5)
        p2_da = (6, 5)

        # get the points in display coordinates
        di = self.large_map_ax.transData.transform([p1_da, p2_da])

        length_in_pixels = di[1, 0] - di[0, 0]
        return (length_in_pixels * 72) / self.fig.dpi

    def _setup_map_figure(self):
        """
        Set fig size ratios according to lat lon ratios
        """
        big_fig_size = 10
        lat = self.config_dict['bounds'][3] - self.config_dict['bounds'][2]
        lon = self.config_dict['bounds'][1] - self.config_dict['bounds'][0]
        # figsize is w x h
        if lat > lon:
            fig = plt.figure(figsize=((lon / lat) * big_fig_size, big_fig_size))
        else:
            fig = plt.figure(figsize=(big_fig_size, (lat / lon) * big_fig_size))
        return fig

    def _find_shape_path(self):
        """
        If path supplied by user, find the shapefile path and set self.reference_reef_shape_file_path.
        else, search for the shape file in the current working directory.
        """
        if self.args.ref_reef_dir:
            # The user has supplied a path
            # This could be the directory containing the parent directory of the dataset
            # It could be the parent directory of the dataset itself
            if 'WCMC008' in self.args.ref_reef_dir:
                potential_shape_path = os.path.join(self.args.ref_reef_dir,
                                                    '01_Data/WCMC008_CoralReef2018_Py_v4.shp')
                if os.path.exists(potential_shape_path):
                    return potential_shape_path
            else:
                # Search for the directory in the supplied path
                dir_to_search = self.args.ref_reef_dir
                return self._search_for_ref_reef_parent_data_dir(dir_to_search=dir_to_search)
        else:
            # No user supplied path, search for the directory in the current working directory
            dir_to_search = self.root_dir
            return self._search_for_ref_reef_parent_data_dir(dir_to_search=dir_to_search)

    def _search_for_ref_reef_parent_data_dir(self, dir_to_search):
        """
        Try to find the directory that holds the subdirectories that lead to the refernce reef shape file.
        """
        candidate_dirs = []
        data_set_parent_dir = None
        for (dirpath, dirnames, filenames) in os.walk(dir_to_search):
            candidate_dirs.extend([os.path.join(dirpath, _) for _ in dirnames if 'WCMC008' in _])

        if len(candidate_dirs) == 1:
            # Then we have found the parent directory
            data_set_parent_dir = candidate_dirs[0]
        else:
            self._report_unable_to_find_ref_reef_path()
        # Verify that the shape file exists
        potential_shape_path = os.path.join(data_set_parent_dir, '01_Data/WCMC008_CoralReef2018_Py_v4.shp')
        if os.path.exists(potential_shape_path):
            return potential_shape_path
        else:
            self._report_unable_to_find_ref_reef_path()

    def _report_unable_to_find_ref_reef_path(self):
        raise RuntimeError(
            "Could not automatically find the reference reef dataset. "
            "Please specify the directory of the dataset on the command line using --ref-reef-dir")

    def _setup_config(self):
        """
        Check the values of the user config inputs
        We will assume that the user will supply either command line arguments
        OR a .tsv/.xlsx config_sheet.
        In the case where a config parameter is referenced in both of these,
        we will use the command line supplied argument but produce a warning for the user that their config sheet
        setting is being overwritten.
        Where no value has been provided for a given config parameter, we will inform the user of this and
        provide the value for the given param to be used.

        Config params are:
        'bounds', 'plot_sea', 'sea_color', 'plot_reference_reefs',
                'reference_reef_color', 'reference_reef_patch_type', 'plot_land', 'land_color',
                'plot_grid_lines', 'lon_grid_line_pos', 'lat_grid_line_pos',
                'lon_grid_lab_pos', 'lat_grid_lab_pos', 'plot_boundaries'
        """
        self._check_bounds()
        self._check_bool_params()
        self._check_color_params()
        self._check_grid_lab_pos()
        self._check_grid_line_coords()
        self._check_ref_reef_patch_type()

    def _check_ref_reef_patch_type(self):
        """
        Check user provided valid value for reference_reef_patch_type or set default
        """
        if self.config_dict['plot_reference_reefs']:
            cl_param_set, config_param_set = self._param_set(param='reference_reef_patch_type')
            self._set_config_param(param='reference_reef_patch_type', cl_param=cl_param_set,
                                   config_param=config_param_set)
            if not self.config_dict['reference_reef_patch_type'] in ['polygon', 'point']:
                self._set_default_param(param='reference_reef_patch_type')

    def _check_grid_line_coords(self):
        for g_line_cords_param in ['lon_grid_line_pos', 'lat_grid_line_pos']:
            cl_param_set, config_param_set = self._param_set(param=g_line_cords_param)
            self._set_config_param(param=g_line_cords_param, cl_param=cl_param_set, config_param=config_param_set)
        self._check_valid_grid_line_coords()

    def _check_valid_grid_line_coords(self):
        """
        Check user supplied grid line coordinates are valid else use default
        """
        if self.config_dict['plot_grid_lines']:
            if self.config_dict['lon_grid_line_pos'] is not None:
                try:
                    assert (len(self.config_dict['lon_grid_line_pos'].split(',')) > 0)
                    [float(_) for _ in self.config_dict['lon_grid_line_pos'].split(',')]
                except Exception:
                    print("WARNING: There is a problem with the formatting of your longitude grid line coordinates.")
                    print('Default coordinates will be used.')
                    self.config_dict['lon_grid_line_pos'] = None
            if self.config_dict['lat_grid_line_pos'] is not None:
                try:
                    assert (len(self.config_dict['lat_grid_line_pos'].split(',')) > 0)
                    [float(_) for _ in self.config_dict['lat_grid_line_pos'].split(',')]
                except Exception:
                    print("WARNING: There is a problem with the formatting of your latitude grid line coordinates.")
                    print('Default coordinates will be used.')
                    self.config_dict['lat_grid_line_pos'] = None

    def _check_grid_lab_pos(self):
        """
        Check for a user input for the grid_lab_pos params and set to default if not.
        """
        for g_lab_pos_param in ['lon_grid_lab_pos', 'lat_grid_lab_pos']:
            cl_param_set, config_param_set = self._param_set(param=g_lab_pos_param)
            self._set_config_param(param=g_lab_pos_param, cl_param=cl_param_set, config_param=config_param_set)
        self._check_valid_grid_lab_pos()

    def _check_valid_grid_lab_pos(self):
        try:
            assert (self.config_dict['lon_grid_lab_pos'] in ['bottom', 'top'])
        except AssertionError:
            raise RuntimeError("lon_grid_lab_pos must be 'bottom' or 'top'")
        try:
            assert (self.config_dict['lat_grid_lab_pos'] in ['left', 'right'])
        except AssertionError:
            raise RuntimeError("lat_grid_lab_pos must be 'left' or 'right'")

    def _check_color_params(self):
        """
        Check the config and user site color parameters provided
        and set the config dict to the default value if necessary.
        """
        # Map config colour params
        for c_param in ['sea_color', 'land_color', 'reference_reef_color']:
            cl_param_set, config_param_set = self._param_set(param=c_param)
            self._set_config_param(param=c_param, cl_param=cl_param_set, config_param=config_param_set)
            if not is_color_like(self.config_dict[c_param]):
                self._set_default_param(param=c_param)

    def _check_bool_params(self):
        for bool_param in [
            'plot_sea', 'plot_reference_reefs', 'plot_land', 'plot_grid_lines', 'plot_boundaries', 'user_site_labels'
        ]:
            cl_param_set, config_param_set = self._param_set(param=bool_param)
            self._set_config_param(param=bool_param, cl_param=cl_param_set, config_param=config_param_set)
            self._check_valid_bool_param(bool_param)

    def _check_valid_bool_param(self, bool_param):
        if self.config_dict[bool_param] in ['TRUE', 'true', 'True', 'T', 't']:
            self.config_dict[bool_param] = True
        elif self.config_dict[bool_param] in ['FALSE', 'false', 'False', 'F', 'f']:
            self.config_dict[bool_param] = False
        elif type(self.config_dict[bool_param] == bool):
            pass
        else:
            raise ValueError(f"{bool_param} must be either TRUE or FALSE.")

    def _check_bounds(self):
        # Check to see if the bounds are set by either the config_sheet or the command line
        cl_param_set, config_param_set = self._param_set(param='bounds')
        # Then there is user supplied value for bounds
        self._set_config_param(param='bounds', cl_param=cl_param_set, config_param=config_param_set)
        self._check_bounds_in_correct_order()
        self._check_bounds_valid_values()

    def _check_bounds_valid_values(self):
        try:
            assert ((self.config_dict['bounds'][0] < 180) and (self.config_dict['bounds'][0] > -180))
            assert ((self.config_dict['bounds'][1] < 180) and (self.config_dict['bounds'][1] > -180))
        except AssertionError:
            raise RuntimeError("One of your longitude bounds appears to be an invalid value.")
        try:
            assert ((self.config_dict['bounds'][2] < 90) and (self.config_dict['bounds'][2] > -90))
            assert ((self.config_dict['bounds'][3] < 90) and (self.config_dict['bounds'][3] > -90))
        except AssertionError:
            raise RuntimeError("One of your latitude bounds appears to be an invalid value.")

    def _check_bounds_in_correct_order(self):
        try:
            assert (self.config_dict['bounds'][0] < self.config_dict['bounds'][1])
        except AssertionError:
            raise RuntimeError('Check the format of your user config sheet.\n'
                               'latitude and longitude valus must be in valid decimal degree format and\n'
                               'westernmost bound should be less than easternmost bound')
        try:
            assert (self.config_dict['bounds'][2] < self.config_dict['bounds'][3])
        except AssertionError:
            raise RuntimeError('Check the format of your user config sheet.\n'
                               'latitude and longitude valus must be in valid decimal degree format and\n'
                               'southernmost bounds should be less than northernmost bound')

    def _set_config_param(self, param, cl_param, config_param):
        if config_param and cl_param:
            print(
                f"WARNING: the {param} parameter has been supplied both in the user "
                f"config sheet ({self.config_dict[param]}) and on the command line ({getattr(self.args, param)}).\n"
                f"The command line-supplied argument will be used."
            )
            if param == 'bounds':
                try:
                    self.config_dict[param] = [float(_) for _ in getattr(self.args, param).split(',')]
                except ValueError:
                    raise RuntimeError("Unable to convert one of the bounds to decimal degree format.\n"
                                       "Please check the formatting of your bounds.")
            else:
                self.config_dict[param] = getattr(self.args, param)
            self._notify_user_set_config_dict_param(param=param)
        elif config_param:
            # Then param only supplied by config_sheet
            # Conduct the check using the config_bounds
            if param == 'bounds':
                try:
                    self.config_dict[param] = [float(_) for _ in self.config_dict[param].split(',')]
                except ValueError:
                    raise RuntimeError("Unable to convert one of the bounds to decimal degree format.\n"
                                       "Please check the formatting of your bounds.")
            else:
                # No need to update the config_dict. Value already correctly set
                pass
            self._notify_user_set_config_dict_param(param=param)
        elif cl_param:
            # Then param only supplied by command line
            if param == 'bounds':
                try:
                    self.config_dict[param] = [float(_) for _ in getattr(self.args, param).split(',')]
                except ValueError:
                    raise RuntimeError("Unable to convert one of the bounds to decimal degree format.\n"
                                       "Please check the formatting of your bounds.")
            else:
                self.config_dict[param] = getattr(self.args, param)
            self._notify_user_set_config_dict_param(param=param)
        else:
            # Then no valid argument set for the param
            # Set param from default dict
            self._set_default_param(param)

    def _set_default_param(self, param):
        print(f'No valid value for {param} provided. Using default.')
        self.config_dict[param] = self.param_defaults_dict[param]
        self._notify_user_set_config_dict_param(param=param)

    def _param_set(self, param):
        """
        Check if a given parameter had a value set via the config sheet or via the command line
        """
        config_param = False
        cl_param = False
        if param in self.config_dict:
            if not pd.isnull(self.config_dict[param]):
                config_param = True
        if getattr(self.args, param):
            cl_param = True
        return cl_param, config_param

    def _notify_user_set_config_dict_param(self, param):
        print(f'{param} set to: {self.config_dict[param]}')

    @staticmethod
    def _define_config_args(parser):
        """
        Command line user input allows for all map config params to be set.

        'bounds', 'plot_sea', 'sea_color', 'plot_reference_reefs',
        'reference_reef_color', 'reference_reef_patch_type', 'plot_land', 'land_color',
        'plot_grid_lines', 'lon_grid_line_pos', 'lat_grid_line_pos',
        'lon_grid_lab_pos', 'lat_grid_lab_pos', 'plot_boundaries'
        """
        parser.add_argument(
            '--bounds',
            help='Comma delimited  coordinate boundaries in decimal degrees (N/E)\n'
                 'in the order of westernmost, easternmost, southermost, northernmost\n.'
                 'E.g. For bounds that encapsulate the Red Sea: 32,45,12,30\n'
                 'E.g. For bounds that encapsulate the GBR: 141,155,-25,-10.19\n'
                 '[-180, 180, -90, 90]',
        )
        parser.add_argument(
            '--plot-sea',
            help='Whether to plot the sea on the map. TRUE|FALSE. [TRUE]',
            required=False
        )
        parser.add_argument(
            '--sea-color',
            help='Sea color as valid matplotlib color.\n'
                 'See here for valid matplotlib color formats: https://matplotlib.org/2.0.2/api/colors_api.html.\n'
                 '[#88b5e0]',
            required=False
        )
        parser.add_argument(
            '--plot-reference-reefs',
            help='Whether to plot the reference reefs on the map. TRUE|FALSE. [TRUE]',
            required=False
        )
        parser.add_argument(
            '--reference-reef-color',
            help='Reference reef color as valid matplotlib color.\n'
                 'See here for valid matplotlib color formats: https://matplotlib.org/2.0.2/api/colors_api.html.\n'
                 '[#003366]',
            required=False
        )
        parser.add_argument(
            '--plot-land',
            help='Whether to plot land on the map. TRUE|FALSE. [TRUE]',
            required=False
        )
        parser.add_argument(
            '--land-color',
            help='Land color as valid matplotlib color.\n'
                 'See here for valid matplotlib color formats: https://matplotlib.org/2.0.2/api/colors_api.html.\n'
                 '[white]',
            required=False
        )
        parser.add_argument(
            '--plot-grid-lines',
            help='Whether to plot grid lines on the map. TRUE|FALSE. [TRUE]',
            required=False
        )
        parser.add_argument(
            '--lon-grid-line-pos',
            help='Comma delimited  coordinates for the longitude grid lines in decimal degrees (N/E)\n'
                 'By default, grid line positions will be plotted automatically'
        )
        parser.add_argument(
            '--lat-grid-line-pos',
            help='Comma delimited  coordinates for the latitude grid lines in decimal degrees (N/E)\n'
                 'By default, grid line positions will be plotted automatically'
        )
        parser.add_argument(
            '--lon-grid-lab-pos',
            help='Which axis to plot the longitude grid lines on. top|bottom. [bottom]',
            required=False
        )
        parser.add_argument(
            '--lat-grid-lab-pos',
            help='Which axis to plot the latitude grid lines on. left|right. [left]',
            required=False
        )
        parser.add_argument(
            '--plot-boundaries',
            help='Whether to plot country boundaries on the map. TRUE|FALSE. [TRUE]',
            required=False
        )
        parser.add_argument(
            '--user-site-labels',
            help='Whether to annotate the user sites with labels. TRUE|FALSE. [TRUE]',
            required=False
        )

    @staticmethod
    def _define_runtime_args(parser):
        """
        User specification of:
            config and site sheet paths
            figure output dir
            reference reef shape file input dir
            whether to plot ref reefs as points
        """
        parser.add_argument(
            '--config-sheet',
            help='The full path to the .xlsx or .tsv file that contains the user configurations for the map',
            required=False
        )
        parser.add_argument(
            '--site-sheet',
            help='The full path to the .xlsx or .tsv file that contains the user site data',
            required=False
        )
        parser.add_argument(
            '--fig-out-dir',
            help='The full path to the directory where the map output figures will be saved. '
                 'A .svg and a .png file will be created with a time stamp.'
        )
        parser.add_argument(
            '--ref-reef-dir',
            help='The full path to the directory containing the reference reef shapefile data.'
                 'Default is current working directory. The dataset can be downloaded from: '
                 'https://data.unep-wcmc.org/datasets/1'
        )
        parser.add_argument(
            '--reference-reef-patch-type',
            help='Whether to plot the reference reefs as polygon or circle patches.\n'
                 'This can be helpful for maps that cover a larger area as '
                 'stroking paths can create some graphical aftefacts. must be "polygon" or "point". [polygon]'
        )

    def draw_map(self):
        land_110m, ocean_110m, boundary_110m = self._get_naural_earth_features_big_map()
        print('Drawing annotations on map\n')
        self._draw_natural_earth_features_big_map(land_110m, ocean_110m, boundary_110m)
        print('Annotations complete\n')
        if self.config_dict['plot_grid_lines']:
            self._put_gridlines_on_large_map_ax()
        self._add_user_reefs()
        self._add_reference_reefs()
        self._save_figs()

    def _save_figs(self):
        print(f'saving to {self.fig_out_path_png}')
        plt.savefig(self.fig_out_path_png, dpi=600)
        print(f'saving to {self.fig_out_path_svg}')
        plt.savefig(self.fig_out_path_svg, dpi=600)

    def _add_user_reefs(self):
        """
        Add the user supplied reefs.
        Currently as scatter, but we should enable polygons too.
        Line widths should be proportional to the marker size
        We should attempt to add the points in order of the largest first to minimise overlap
        """
        self._plot_user_points()
        self._annotate_site_labels()

    def _plot_user_points(self):
        print('plotting user reefs\n')
        line_widths = ((self.site_df['radius_in_deg_lat'].astype(
            float) * 2) * self.coord_to_point_scaler) * 0.1
        self.large_map_ax.scatter(
            x=self.site_df['longitude_deg_e'],
            y=self.site_df['latitude_deg_n'],
            s=(((self.site_df['radius_in_deg_lat'].astype(
                float) * 2) * self.coord_to_point_scaler) ** 2),
            facecolors=self.site_df['facecolor'],
            edgecolors=self.site_df['edgecolor'], zorder=3,
            linewidths=line_widths
        )

    def _annotate_site_labels(self):
        if self.config_dict['user_site_labels']:
            for ind in self.site_df.index:
                self.large_map_ax.annotate(
                    ind,
                    (
                        self.site_df.at[ind, 'longitude_deg_e'] + self.site_df.at[ind, 'radius_in_deg_lat'],
                        self.site_df.at[ind, 'latitude_deg_n'] + self.site_df.at[ind, 'radius_in_deg_lat']
                    )
                )

    def _add_reference_reefs(self):
        """
        Parse through the reference reef records from the shapely file, and if within bounds of the map
        plot them on the map either as polygons or points depending on the user config.

        NBWe were working with shapely features and adding geometries but there were so many problems
        I advise to stay away form trying to get them working again.
        Instead we are now creating individual Polygon patches from the coordinates or plotting a point (via scatter)
        for each of the coordinate points that make up a reef polygon.
        """
        print('Annotating reference reefs\n')
        reader = Reader(self.reference_reef_shape_file_path)
        error_count = 0
        reef_count = 0
        checked_count = 0
        point_coords_x = []
        point_coords_y = []
        start_time = time.time()
        for r in reader.records():  # reader.records() produces a generator
            try:
                if r.geometry.geom_type.lower() == 'multipolygon':
                    checked_count, reef_count = self._handle_multipolygon(
                        checked_count, point_coords_x, point_coords_y, r, reef_count, start_time
                    )
                elif r.geometry.geom_type.lower() == 'polygon':
                    checked_count, reef_count = self._handle_polygon(
                        checked_count, point_coords_x, point_coords_y, r, reef_count, start_time
                    )
            except Exception:
                # The common error that occurs is Unexpected Error: unable to find ring point
                # We've given up trying to catch this is a more elegant way
                # The class of exception raised is Exception in shapefile.py
                error_count += 1
                continue

        num_indi_points = self._plot_coords_as_points(point_coords_x, point_coords_y)

        self._report_on_ref_reef_plotting(error_count, num_indi_points, reef_count)

    def _report_on_ref_reef_plotting(self, error_count, num_indi_points, reef_count):
        print(f'\n{error_count} error producing records were discounted from the reference reefs')
        if self.config_dict['reference_reef_patch_type'] == 'point':
            print(f'{reef_count} reference reefs were added to the plot as {num_indi_points} individual points')
        else:
            print(f'{reef_count} reference reefs were added to the plot')

    def _plot_coords_as_points(self, point_coords_x, point_coords_y):
        num_indi_points = None
        if self.config_dict['reference_reef_patch_type'] == 'point':
            # _make_and_add_ref_reef_patches will only return num_indi_points
            # when self.config_dict['reference_reef_patch_type'] == 'point'
            num_indi_points = self._make_and_add_ref_reef_patches(coords=(point_coords_x, point_coords_y))
        return num_indi_points

    def _handle_polygon(self, checked_count, point_coords_x, point_coords_y, r, reef_count, start_time):
        checked_count += 1
        if checked_count % 1000 == 0:
            self._report_checked_reef_number(checked_count, start_time)
        if self._if_within_bounds(r.bounds):
            coords = r.geometry.exterior.coords.xy
            self._plot_poly_or_collect_coords(coords, point_coords_x, point_coords_y)
            reef_count += 1
            if reef_count % 100 == 0:
                self._report_reef_number_plotted(reef_count)
        return checked_count, reef_count

    def _handle_multipolygon(self, checked_count, point_coords_x, point_coords_y, r, reef_count, start_time):
        # Create multiple matplotlib polygon objects from the multiple shape polygons
        for polygon in r.geometry:
            checked_count += 1
            if checked_count % 1000 == 0:
                self._report_checked_reef_number(checked_count, start_time)
            if self._if_within_bounds(polygon.bounds):
                # each of the individual coords is a tup of tups
                coords = polygon.exterior.coords.xy
                self._plot_poly_or_collect_coords(coords, point_coords_x, point_coords_y)
                reef_count += 1
                if reef_count % 100 == 0:
                    self._report_reef_number_plotted(reef_count)
        return checked_count, reef_count

    def _plot_poly_or_collect_coords(self, coords, point_coords_x, point_coords_y):
        if self.config_dict['reference_reef_patch_type'] == 'point':
            # Then we want to collect all of the xy points to plot as a scatter
            # and plot them as a single scatter at the end
            point_coords_x.append(np.array(coords[0]))
            point_coords_y.append(np.array(coords[1]))
        else:
            # we want to plot the polygons as we go
            self._make_and_add_ref_reef_patches(coords)

    def _report_reef_number_plotted(self, reef_count):
        print(f'{reef_count} reference reefs plotted')

    def _report_checked_reef_number(self, checked_count, start_time):
        new_time = time.time()
        print(f'{checked_count} reference polygons checked in {new_time - start_time:.2f}s')

    def _make_and_add_ref_reef_patches(self, coords):
        """
        When self.config_dict['reference_reef_patch_type'] == 'point' we will plot the reference
        reefs as cirlces on the map using scatter.
        We were originally doing this using Circle patches and then either adding them to the plot
        as individual patches or as part of a PatchCollection. However, this is very slow when
        working with larger numbers of reefs. It is slow to add the patches to the ax, but it is
        also very slow to write out the figure as .png and .svg
        It is much faster to use scatter to plot the points. This also leads to a much faster write speed for the
        figure.
        """
        if self.config_dict['reference_reef_patch_type'] == 'point':
            coords_x = self._plot_ref_scatter(coords)
            return len(coords_x)
        else:
            self._make_and_add_poly(coords)

    def _plot_ref_scatter(self, coords):
        coords_x, coords_y = self._concat_input_coord_arrays(coords)
        point_size = self._calc_ref_point_size()
        self.large_map_ax.scatter(x=coords_x, y=coords_y, s=point_size ** 2, zorder=2,
                                  facecolors=self.config_dict['reference_reef_color'], edgecolors='none')
        return coords_x

    def _concat_input_coord_arrays(self, coords):
        coords_x = np.concatenate(coords[0])
        coords_y = np.concatenate(coords[1])
        return coords_x, coords_y

    def _calc_ref_point_size(self):
        # A sensible size is perhaps 1/500th of the shortest size
        lat = self.config_dict['bounds'][3] - self.config_dict['bounds'][2]
        lon = self.config_dict['bounds'][1] - self.config_dict['bounds'][0]
        if lat > lon:
            deg_size = lon / 500
        else:
            deg_size = lat / 500
        point_size = self.coord_to_point_scaler * deg_size
        return point_size

    def _make_and_add_poly(self, coords):
        reef_poly = Polygon([(x, y) for x, y in zip(list(coords[0]), list(coords[1]))],
                            closed=True, fill=True, edgecolor=self.config_dict['reference_reef_color'], linewidth=1,
                            facecolor=self.config_dict['reference_reef_color'],
                            alpha=1, zorder=2)
        self.large_map_ax.add_patch(reef_poly)

    def _if_within_bounds(self, bounds):
        """
        Check bounds for a given polygon lie within the bounds for the map
        """
        if bounds[0] > self.config_dict['bounds'][0]:
            if bounds[1] > self.config_dict['bounds'][2]:
                if bounds[2] < self.config_dict['bounds'][1]:
                    if bounds[3] < self.config_dict['bounds'][3]:
                        return True
        return False

    @staticmethod
    def _get_naural_earth_features_big_map():
        land_110m = cartopy.feature.NaturalEarthFeature(category='physical', name='land',
                                                        scale='50m')
        ocean_110m = cartopy.feature.NaturalEarthFeature(category='physical', name='ocean',
                                                         scale='50m')
        boundary_110m = cartopy.feature.NaturalEarthFeature(category='cultural',
                                                            name='admin_0_boundary_lines_land', scale='110m')
        return land_110m, ocean_110m, boundary_110m

    @staticmethod
    def _get_naural_earth_features_zoom_map():
        land_10m = cartopy.feature.NaturalEarthFeature(category='physical', name='land',
                                                       scale='50m')
        ocean_10m = cartopy.feature.NaturalEarthFeature(category='physical', name='ocean',
                                                        scale='50m')

        return land_10m, ocean_10m

    def _draw_natural_earth_features_big_map(self, land_110m, ocean_110m, boundary_110m):
        """NB the RGB must be a tuple in a list and the R, G, B must be given as a value between 0 and 1"""
        # self.large_map_ax.add_feature(land_110m, facecolor=[(238 / 255, 239 / 255, 219 / 255)],
        #                               edgecolor='black', linewidth=0.2)
        if self.config_dict['plot_land']:
            self.large_map_ax.add_feature(land_110m, facecolor=self.config_dict['land_color'],
                                          edgecolor='black', linewidth=0.2, zorder=1)
        if self.config_dict['plot_sea']:
            self.large_map_ax.add_feature(ocean_110m, facecolor=self.config_dict['sea_color'],
                                          edgecolor='black', linewidth=0.2)
        if self.config_dict['plot_boundaries']:
            self.large_map_ax.add_feature(boundary_110m, edgecolor='gray', linewidth=0.2, facecolor='None')

    def _put_gridlines_on_large_map_ax(self):
        """
        A note on how to plot gridlines using cartopy:
        Although there is a GeoAxis.gridlines() method, this method does not yet allow a lot of
        bespoke options. If we want to only put the labels on the top and left then we have to
        generate a Gridliner object (normally returned by GeoAxis.gridlines() ourselves. We then need
        to manually change the xlabels_bottom and ylabels_right attributes of this Gridliner object.
        We then draw it by adding it to the GeoAxis._gridliners list.
        """
        if self.config_dict['lon_grid_line_pos'] and self.config_dict['lat_grid_line_pos']:
            xlocs = mticker.FixedLocator([float(_) for _ in self.config_dict['lon_grid_line_pos'].split(',')])
            ylocs = mticker.FixedLocator([float(_) for _ in self.config_dict['lat_grid_line_pos'].split(',')])
            g1 = Gridliner(
                axes=self.large_map_ax, crs=ccrs.PlateCarree(), draw_labels=True,
                xlocator=xlocs, ylocator=ylocs)
        else:
            g1 = Gridliner(
                axes=self.large_map_ax, crs=ccrs.PlateCarree(), draw_labels=True)
        if self.config_dict['lon_grid_lab_pos'] == 'bottom':
            g1.top_labels = False
        else:
            g1.bottom_labels = False
        if self.config_dict['lat_grid_lab_pos'] == 'left':
            g1.right_labels = False
        else:
            g1.left_labels = False
        self.large_map_ax._gridliners.append(g1)

mwif = MapWthInsetFigure()
mwif.draw_map()
