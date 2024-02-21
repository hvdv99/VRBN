import logging
import os
import sys
import datetime
from dotenv import load_dotenv

from flask import Flask, request, render_template, send_from_directory, url_for, flash, redirect
from google.cloud import storage

from project.vectara import query_corpus, list_documents, extract_titles, generate_token, upload_to_vectara

load_dotenv('.flaskenv')
FLASK_ENVIRONMENT = os.getenv('FLASK_ENVIRONMENT')
if FLASK_ENVIRONMENT == 'development':
    from google.oauth2 import service_account
    load_dotenv('.env')
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
else:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = os.environ.get('SECRET_KEY')

token = {'access_token': None, 'expires': None}
documents = None


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'GET':
        return render_template('query.html')
    elif request.method == 'POST':
        check_token_and_update_document_list()
        query = request.form.get('query', 'Not found')
        sentences_context = request.form.get('sentences_context', 3)
        num_docs = request.form.get('num_docs', 10)
        num_docs_summary = request.form.get('num_docs_summary', 5)
        lambda_par = request.form.get('range-lambda', 0.025)
        vectara_response = query_corpus(query, token['access_token'], num_docs,
                                        sentences_context, lambda_par, num_docs_summary).get('responseSet', None)
        responses = vectara_response[0].get('response', None)
        documents = vectara_response[0].get('document', None)
        summary = vectara_response[0].get('summary', 'Geen samenvatting beschikbaar')
        if summary[0].get('status', None):
            status_code = summary[0].get('status', None)[0].get('code')
            status_detail = summary[0].get('status')[0].get('statusDetail')
            flash(f"Error: {status_code}: {status_detail}", 'error')
        return render_template(
            'response.html',
                               query=query,
                               responses=responses,
                               documents=documents,
                               summary=summary,
                               lambda_par=lambda_par,
                               enumerate=enumerate
                               )


@app.route('/sources')
def sources():
    check_token_and_update_document_list()
    filename_title_mapper = extract_titles(documents)  # global documents is list of dicts
    return render_template("sources.html",
                           filename_title_mapper=filename_title_mapper,
                           enumerate=enumerate)


@app.route('/about')
def about():
    return render_template("about.html")


@app.route('/documents/<path:filename>', methods=['GET'])
def document(filename):

    if not os.path.exists(os.path.join('project', app.config['UPLOAD_FOLDER'], filename)):
        download_response = download_file_from_bucket(filename)

        if not download_response:
            logging.info(f"File {filename} does not exist")
            flash('Bestand niet gevonden, controleer de bronnen', 'warning')
            return redirect(url_for('sources'))

    else:
        logging.info(f"Retrieved {filename} locally")

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)


def download_file_from_bucket(filename):
    project_id = os.environ.get('PROJECT_ID')
    bucket_name = os.environ.get('BUCKET_NAME')

    if FLASK_ENVIRONMENT == 'development':
        credentials = service_account.Credentials.from_service_account_file(
            os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        )
        client = storage.Client(project=project_id, credentials=credentials)
    else:
        client = storage.Client(project=project_id)

    bucket = client.get_bucket(bucket_name)
    blob = bucket.blob(filename)

    if not blob.exists():
        return False
    else:
        if not os.path.exists(os.path.join('project', app.config['UPLOAD_FOLDER'])):
            os.makedirs(os.path.join('project', app.config['UPLOAD_FOLDER']))
        local_filename = os.path.join('project', app.config['UPLOAD_FOLDER'], filename)
        blob.download_to_filename(local_filename)
        logging.info(f"Downloaded: {local_filename}")
        return True


def check_token_and_update_document_list():
    if token['expires'] is None or token['expires'] <= datetime.datetime.now():
        token_response = generate_token()
        token['access_token'] = token_response.get('access_token')
        token['expires'] = (datetime.datetime.now() +
                            datetime.timedelta(seconds=token_response.get('expires_in')))

        update_vectara_document_list()
        not_in_vectara = compare_files()

        if not_in_vectara:
            for filename in not_in_vectara:
                download_file_from_bucket(filename)
                upload_to_vectara(filename, token['access_token'])
                update_vectara_document_list()


def update_vectara_document_list():
    global documents
    documents = list_documents(access_token=token['access_token'])
    logging.info(f"Updated documents list")


def list_blobs():
    bucket_name = os.environ.get('BUCKET_NAME')
    project_id = os.environ.get('PROJECT_ID')

    if FLASK_ENVIRONMENT == 'development':
        credentials = service_account.Credentials.from_service_account_file(
            os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        )
        storage_client = storage.Client(project=project_id, credentials=credentials)
    else:
        storage_client = storage.Client(project=project_id)

    blobs = storage_client.list_blobs(bucket_name)

    files_in_bucket = []
    for blob in blobs:
        files_in_bucket.append(blob.name)
    logging.info("Retrieved filelist from bucket")
    return files_in_bucket


def compare_files():
    files_in_bucket = set(list_blobs()) - {'slides-oplevering-21-02-2024.pdf'}
    vectara_filenames = set(extract_titles(documents).keys())
    not_in_vectara = list(files_in_bucket - vectara_filenames)
    logging.info(f"Files not in vectara: {not_in_vectara}")
    return not_in_vectara


if __name__ == "__main__":
    app.run(debug=True)
