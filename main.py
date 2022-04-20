import json
import random
import string
from dataclasses import asdict
from time import sleep

from escriptorium_connector import EscriptoriumConnector
import os
from dotenv import load_dotenv
from escriptorium_connector.dtos import GetLine
import requests
from shapely.geometry import Point, Polygon
from requests.compat import urljoin
import numpy as np

escriptorium_url = str(os.getenv('ESCRIPTORIUM_URL'))
token = '80af7b3939ffe4530e4a27b98bd7664cd5e59b23'
headers = {'Authorization': 'Token ' + token}

regions_type_list = []


def update_coords(coords: list, shift_value: int):
    updated = [[x, y + shift_value] for [x, y] in coords]
    return updated


def id_generator(size, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


def create_mask_from_baseline(baseline):
    x_1, x_2, y_1, y_2 = baseline[0][0], baseline[1][0], baseline[0][1], baseline[1][1]
    new_mask = [[x_1, y_1 - 10], [x_2, y_1 - 10], [x_2, y_1 + 10], [x_1, y_1 + 10]]
    return new_mask


class Page:
    """
    Hack to re-compute polygons for first and last line of each given zone.
    """

    def __init__(self, document_pk, page_pk):
        self.document_pk = document_pk
        self.region_types = None
        self.part_list = []
        self.page_pk = page_pk
        self.correct_labels = ["MainZone"]
        self.main_zone_typology_pk = None

        load_dotenv('my.env')
        self.escriptorium_url = str(os.getenv('ESCRIPTORIUM_URL'))
        username = str(os.getenv('ESCRIPTORIUM_USERNAME'))
        password = str(os.getenv('ESCRIPTORIUM_PASSWORD'))
        self.escr_connect = EscriptoriumConnector(self.escriptorium_url, username, password)
        # self.document = escr.get_document(pk=self.document_pk)

    def get_pages(self):
        self.get_page(1)

    def get_page(self, page):
        url = f"{self.escriptorium_url}/api/documents/{self.document_pk}/parts/?page={page}"
        res = requests.get(url, headers=headers)
        try:
            data = res.json()
        except json.decoder.JSONDecodeError as e:
            print(res)
        else:
            for part in data['results']:
                self.part_list.append(part['pk'])
            if data['next']:
                self.get_page(page + 1)

    def reset_masks(self, page_pk, lines):
        lines = ",".join([str(line) for line in lines])
        base_url = f'{self.escriptorium_url}/api/documents/{self.document_pk}/parts/{page_pk}/reset_masks/?only={lines}'
        requests.post(base_url, headers=headers)

    def get_region_types(self):
        document_base_json = requests.get(f'{self.escriptorium_url}/api/documents/{self.document_pk}/',
                                          headers=headers).json()

        self.region_types = {element['pk']: element['name'] for element in document_base_json['valid_block_types']}

    def get_lines_from_region(self):
        parts_url = f'{self.escriptorium_url}/api/documents/{self.document_pk}/parts/{self.page_pk}'
        res = requests.get(parts_url, headers=headers).json()
        regions = res["regions"]
        lines = res["lines"]
        dictionnary = {}
        simplified_regions = []
        for region in regions:
            id = region['pk']
            typology = region['typology']
            dictionnary[id] = self.region_types[typology]
            if self.region_types[typology] == "MainZone":
                self.main_zone_typology_pk = typology
                simplified_regions.append(id)
        id_order_typology_list = []
        # we create a list of tuples of the form (line_id, line_order, parent_region_id, parent_region_label)
        for line in res['lines']:
            try:
                order_region = (line['pk'], line['order'], line['region'], dictionnary[line['region']], line['baseline'])
                print(line['region'])
            except:
                print(line)
                print(dictionnary[line['region']])
                print(line['baseline'])
            id_order_typology_list.append(order_region)

        # we filter this list to get only the wanted labeled zone (default: MainZone from segmOnto)
        id_order_typology_list = [tuple for tuple in id_order_typology_list if tuple[3] in self.correct_labels]

        # We get the first and last line of each region
        list_of_baselines = []
        for region_pk in simplified_regions:
            lines_per_region = [line[0] for line in id_order_typology_list if line[2] == region_pk]
            try:
                first_line = min([line for line in id_order_typology_list if line[2] == region_pk], key=lambda x: x[1])
                last_line = max([line for line in id_order_typology_list if line[2] == region_pk], key=lambda x: x[1])
            except:
                continue
            print(first_line)
            print(last_line)
            # Then we can take the first and the last line, append or prepend a line, re-compute polygons, delete this
            # line, and that's it !
            baselines = [line["baseline"] for line in lines if line['pk'] in lines_per_region]
            baselines = [(x, y) for baseline in baselines for x, y in baseline]

            # On calcule les coordonnées moyennes en abcisse
            mean_starting_x = round(np.mean([baselines[n][0] for n in range(len(baselines) - 1) if n % 2 == 0]))
            mean_ending_x = round(np.mean([baselines[n][0] for n in range(len(baselines) - 1) if n % 2 == 1]))

            # Et la distance moyenne entre chaque ligne
            coefficient = .7
            mean_distance_between_lines = round(
                np.mean([abs(baselines[n][1] - baselines[n + 2][1]) for n in range(len(baselines) - 2) if n % 2 == 0]))*coefficient

            # On crée la baseline de la première ligne virtuelle
            new_first_line = [[mean_starting_x, first_line[4][0][1] - mean_distance_between_lines],
                              [mean_ending_x, first_line[4][1][1] - mean_distance_between_lines]]
            new_last_line = [[mean_starting_x, last_line[4][0][1] + mean_distance_between_lines],
                             [mean_ending_x, last_line[4][1][1] + mean_distance_between_lines]]

            list_of_baselines.append(new_first_line)
            list_of_baselines.append(new_last_line)

        return list_of_baselines

    def create_line(self, line_pk, order, region, baseline, mask):
        '''

        :param line_pk:
        :param id:
        :param order:
        :param region:
        :param baseline: la nouvelle baseline
        :param mask:
        :return:
        '''
        newLine = GetLine(pk=line_pk,
                          document_part=self.page_pk,
                          external_id=id,
                          order=order,
                          region=region,
                          baseline=baseline,
                          mask=mask,
                          typology=1,
                          transcriptions=[])
        self.escr_connect.create_document_part_line(doc_pk=self.document_pk, part_pk=self.page_pk, new_line=newLine)

    def delete_line(self, line_pk):
        self.escr_connect.delete_document_part_line(doc_pk=self.document_pk, part_pk=self.page_pk, line_pk=line_pk)


if __name__ == '__main__':
    # Access document number 25 and page with id 6063
    MyDocument = Page(document_pk=25, page_pk=6084)

    # Retrieve pages pk
    # MyDocument.get_pages()

    # Retrieve zones
    MyDocument.get_region_types()

    # Retrieve lines for each document
    baseline_list = MyDocument.get_lines_from_region()

    # Create lines
    id_list = []
    for baseline in baseline_list:
        print("Baseline:")
        print(baseline)
        id = id_generator(8, '1234567890')
        id_list.append(id)
        new_mask = create_mask_from_baseline(baseline)
        MyDocument.create_line(line_pk=id,
                               order=1,
                               region=MyDocument.main_zone_typology_pk,
                               baseline=baseline,
                               mask=new_mask
                               )
    ids = [348051, 348096, 348098, 348143]
    MyDocument.reset_masks(page_pk=MyDocument.page_pk, lines=ids)
    print("Sleeping now")
    #sleep(20)
    print("Deleting the line")
    #[MyDocument.delete_line(line_pk=id) for id in id_list]
