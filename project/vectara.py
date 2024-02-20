import json
import argparse
import requests
import os
import logging
import sys


def generate_token():
    PERSONAL_API_URL = os.environ.get('API_URL')

    if os.getenv('FLASK_ENVIRONMENT') == 'development':
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    else:
        logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials",
        "client_id": os.environ.get('CLIENT_ID'),
        "client_secret": os.environ.get('CLIENT_SECRET')
    }

    response = requests.post(PERSONAL_API_URL, headers=headers, data=data)

    if response.ok:
        logging.info("Successfully generated token")
        return response.json()
    else:
        logging.info(f"Error: {response.status_code}: {response.text}")


def query_corpus(query, access_token,
                 num_docs=20, sentences_context=2, lambda_par=0.25, num_docs_summary=4):

    VECTARA_QUERY_URL = "https://api.vectara.io/v1/query"

    num_docs = int(num_docs)
    sentences_context = int(sentences_context)
    num_docs_summary = int(num_docs_summary)

    if os.getenv('FLASK_ENVIRONMENT') == 'development':
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    else:
        logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    payload = json.dumps({
        "query": [
            {
                "query": query,
                "start": 0,
                "numResults": num_docs,
                "contextConfig": {
                    "sentencesBefore": sentences_context,
                    "sentencesAfter": sentences_context,
                    "startTag": "<b>",
                    "endTag": "</b>"
                },
                "corpusKey": [
                    {
                        "customerId": f'{os.environ["CUSTOMER_ID"]}',
                        "corpusId": 1,
                        "semantics": "DEFAULT",
                        "lexicalInterpolationConfig": {
                            "lambda": lambda_par
                        }
                    }
                ],
                "summary": [
                    {
                        "summarizerPromptName": "vectara-summary-ext-v1.2.0",
                        "maxSummarizedResults": num_docs_summary,
                        "responseLang": "nld"
                    }
                ]
            }
        ]
    }
    )

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'customer-id': os.environ['CUSTOMER_ID'],
        'Authorization': f'Bearer {access_token}'
    }

    logging.info(f"value of lambda: {lambda_par}")
    response = requests.request("POST", VECTARA_QUERY_URL, headers=headers, data=payload)
    logging.info(f"Vectara response received")
    return response.json()


def list_documents(access_token):

    VECTARA_DOCUMENT_URL = "https://api.vectara.io/v1/list-documents"

    if os.getenv('FLASK_ENVIRONMENT') == 'development':
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    else:
        logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    payload = json.dumps({
        "corpusId": 1,
        "numResults": 1000,
        "pageKey": "",
        "metadataFilter": ""
    })

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'customer-id': f'{os.environ["CUSTOMER_ID"]}',
        'Authorization': f'Bearer {access_token}'
    }

    response = requests.request("POST", VECTARA_DOCUMENT_URL, headers=headers, data=payload)
    response_json = response.json()
    vectara_documents = response_json.get('document', None)  # is a list of dicts

    logging.info(f"Retrieved document list from vectara")
    return vectara_documents


def extract_titles(documents):
    filename_title_mapper = {}
    for i, document in enumerate(documents):
        filename = document.get('id', None)
        metadata = document.get('metadata', None)
        num_document = i
        for meta_dict in metadata:
            possible_title = meta_dict.get('name', None)
            if possible_title == 'title':
                filename_title_mapper[filename] = {'title': meta_dict.get('value', None),
                                                   'num_document': num_document}
                break

    return filename_title_mapper


def upload_to_vectara(document_filename, access_token):
    session = requests.Session()

    files = {
        "file": (document_filename,
                 open(os.path.join("project", "uploads", document_filename), "rb"),
                 "application/octet-stream")
    }

    post_headers = {
        "authorization": f"Bearer {access_token}"
    }

    response = session.post(
        url=f"https://api.vectara.io/v1/upload?c={os.environ['CUSTOMER_ID']}&o=1&d=false",
        headers=post_headers,
        files=files)

    logging.info(f"Responsecode: {response.text} Uploaded file to Vectara")
    session.close()


# for testing purposes
def parse_command_line_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', type=str, help="The users query to the corpus")
    parser.add_argument('--num_docs', type=int, default=5, help="Number of documents matches to retrieve")
    parser.add_argument('--num_docs_summary', type=int, default=5, help="Number of documents to summarize")
    parser.add_argument('--sentences_context', type=int, default=3,
                        help="Number of sentences to retrieve around the query match")
    args = parser.parse_args()
    return vars(args)


if __name__ == "__main__":
    generate_token()
