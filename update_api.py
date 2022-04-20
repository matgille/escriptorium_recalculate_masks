import glob
import requests

url = 'http://127.0.0.1:8080/api/documents/25/parts/'
token = '80af7b3939ffe4530e4a27b98bd7664cd5e59b23'
headers = {'Authorization': 'Token ' + token}

myfiles = [glob.glob(f'pg_{i}.png')[0] for i in range(1, 350)]

for folio in myfiles:
    print(folio)
    with open(folio, 'rb') as fh:
        data = {'name': f'{folio}'}
        res = requests.post(url, data=data, files={'image': fh}, headers=headers)