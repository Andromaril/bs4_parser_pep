import logging
import re
from collections import Counter
from urllib.parse import urljoin

import requests_cache
from bs4 import BeautifulSoup
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import BASE_DIR, EXPECTED_STATUS, MAIN_DOC_URL, PEP_URL
from outputs import control_output
from utils import find_tag, get_response


def whats_new(session):
    """собирает ссылки на статьи о нововведениях в Python"""

    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')

    response = get_response(session, whats_new_url)
    if response is None:
        return
    soup = BeautifulSoup(response.text,
                         features='lxml')
    main_div = find_tag(soup, 'section',
                        attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div',
                           attrs={'class': 'toctree-wrapper compound'})
    sections_by_python = div_with_ul.find_all(
                                    'li', attrs={'class': 'toctree-l1'})

    results = [('Ссылка на статью', 'Заголовок', 'Редактор, Автор')]

    for section in tqdm(sections_by_python):
        version_a_tag = find_tag(section, 'a')
        href = version_a_tag['href']
        version_link = urljoin(whats_new_url, href)
        response = get_response(session, version_link)
        if response is None:
            continue
        soup = BeautifulSoup(response.text, features='lxml')
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append((version_link, h1.text, dl_text))
    return results


def latest_versions(session):
    """Собирает информацию о статусах версий Python."""

    MAIN_DOC_URL = 'https://docs.python.org/3/'

    response = get_response(session, MAIN_DOC_URL)
    if response is None:
        return
    soup = BeautifulSoup(response.text, 'lxml')
    sidebar = find_tag(soup, 'div',
                       attrs={'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break

    else:
        raise Exception('Ничего не нашлось')

    results = [('Ссылка на документацию', 'Версия', 'Статус')]

    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append(
            (link, version, status)
        )
    return results


def download(session):
    """cкачивает архив с актуальной документацией."""

    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')

    response = get_response(session, downloads_url)

    if response is None:
        return

    soup = BeautifulSoup(response.text, features='lxml')
    main_tag = find_tag(soup, 'div', {'role': 'main'})
    table_tag = find_tag(main_tag, 'table', {'class': 'docutils'})
    pdf_a4_tag = find_tag(table_tag, 'a',
                          {'href': re.compile(r'.+pdf-a4\.zip$')})
    pdf_a4_link = pdf_a4_tag['href']
    archive_url = urljoin(downloads_url, pdf_a4_link)
    filename = archive_url.split('/')[-1]
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename
    response = session.get(archive_url)

    with open(archive_path, 'wb') as file:
        file.write(response.content)

    logging.info(f'Архив был загружен и сохранён: {archive_path}')


def pep(session):
    """парсинг документов PEP, собирает информацию о количестве статусов"""

    pep_url = PEP_URL
    response = get_response(session, pep_url)

    if response is None:
        return

    soup = BeautifulSoup(response.text, features='lxml')
    pep_td = soup.find_all('td', attrs={'class': 'num'})

    result = []
    for teg in tqdm(pep_td):
        table_status = teg.find_previous('td')
        table_status2 = table_status.text[1:]

        pep_a = find_tag(teg, 'a', attrs={'class': 'reference external'})
        href = pep_a['href']
        version_link = urljoin(pep_url, href)
        response = get_response(session, version_link)

        if response is None:
            continue

        soup = BeautifulSoup(response.text, features='lxml')
        status = soup.find('dt', string="Status")
        status2 = status.find_next('dd')
        result.append(status2.text)

        for key, value in EXPECTED_STATUS.items():
            if key == table_status2:
                if status2.text not in value:
                    logging.info(f'Несовпадающие статусы: \n'
                                 f'{version_link} \n'
                                 f'Статус в карточке: {status2.text} \n'
                                 f'Ожидаемые статусы: {value}')

    table = [('Cтатус', 'Количество')]
    list_result = Counter(result)
    sum2 = sum(list_result.values())
    list_result['Total'] = sum2
    for key, value in list_result.items():
        if key != 'April Fool!':
            table.append((key, value))
    return table


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():

    configure_logging()
    logging.info('Парсер запущен!')

    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')

    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()

    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
