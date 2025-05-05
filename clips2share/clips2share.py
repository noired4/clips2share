# Support for direct script execution
# This is a workaround for running the script directly without installing it as a package.
if __name__ == "__main__" and __package__ is None:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

# End of workaround

import argparse
import configparser
import os
import requests
import time
from bs4 import BeautifulSoup
from dataclasses import dataclass
from importlib.resources import files
from jinja2 import Environment, FileSystemLoader
from os import getenv, makedirs, symlink, link
from os.path import basename, isfile, splitext
from platformdirs import user_config_dir
from shutil import move
from torf import Torrent
from urllib.parse import quote
from vcsi import vcsi
from clips2share import qbittorrent_client
from clips2share import torznab
from pathlib import Path

@dataclass
class Tracker:
    announce_url: str
    category: str
    source_tag: str
    torznab_url: str

@dataclass
class C4SData:
    title: str
    studio: str
    price: str
    date: str
    duration: str
    size: str
    format: str
    resolution: str
    description: str
    category: str
    related_categories: list[str]
    keywords: list[str]
    url: str
    image_url: str

def extract_clip_data(url: str) -> C4SData:
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    title = soup.find('h1').get_text(strip=True)
    studio = soup.find('a', attrs={'data-testid': 'clips-page-studio-link'}).text.strip()
    price = soup.find('span', attrs={'data-testid': 'clip-page-clipPrice'}).text.strip()
    date = soup.find('span', attrs={'data-testid': 'individualClip-clip-date-added'}).text.strip()
    duration = soup.find('span', attrs={'data-testid': 'individualClip-clip-duration'}).text.strip()
    size = soup.find('span', attrs={'data-testid': 'individualClip-clip-size'}).text.strip()
    format = soup.find('span', attrs={'data-testid': 'individualClip-clip-format'}).text.strip()
    resolution = soup.find('span', attrs={'data-testid': 'individualClip-clip-resolution'}).text.strip()
    description = soup.find('div', class_='read-more--text').get_text(separator=' ', strip=True)
    category = soup.find('a', attrs={'data-testid': 'clip-page-clipCategory'}).text.strip()
    related_categories = [ category for category in
                           soup.find('span', attrs={'data-testid': 'clip-page-relatedCategories'}).text.split(',') ]
    keywords = [ keyword for keyword in
                 soup.find('span', attrs={'data-testid': 'clip-page-keywords'}).text.split(',')]
    image_url = soup.find('img', class_='w-full absolute top-0 left-0')['src']

    return C4SData(
        title=title,
        studio=studio,
        price=price,
        date=date,
        duration=duration,
        size=size,
        format=format,
        resolution=resolution,
        description=description,
        category=category,
        related_categories=related_categories,
        keywords=keywords,
        url=url,
        image_url=image_url
    )


def chevereto_image_upload(img_path, chevereto_host, chevereto_api_key):
    """
    Uploads an image to given chevereto instance and returns the image url on success
    """
    payload = {'key': chevereto_api_key, 'format': 'json'}
    r = requests.post(f'https://{chevereto_host}/api/1/upload', data=payload, files=dict(source=open(img_path, 'rb')))
    if r.json()['status_code'] == 200:
        return r.json()['image']['url']
    else:
        raise RuntimeError(r.json())

def format_tags_with_dots(source_list):
    return [s.replace(' ', '.') for s in source_list]

def print_torrent_hash_process(torrent, filepath, pieces_done, pieces_total):
    print(f'[{filepath}] {pieces_done/pieces_total*100:3.0f} % done')

def get_font_path():
    return str(files('clips2share') / 'fonts')

def parse_arguments():
    parser = argparse.ArgumentParser(description="clips2share CLI")
    parser.add_argument('-V', '--video', type=str, help="Path to the video file")
    parser.add_argument('-u', '--url', type=str, help="Clip Store URL")
    parser.add_argument('-D', '--delay-seconds', type=int, help="Auto-continue delay in seconds after torrent is created")
    return parser.parse_args()

def main():
    args = parse_arguments()
    config_path = getenv('C2S_CONFIG_PATH') if getenv('C2S_CONFIG_PATH') else user_config_dir(appname='clips2share') + '/config.ini'
    if not isfile(config_path):
        print(f'config_path {config_path} does not exists, download example config here: '
              f'https://codeberg.org/c2s/clips2share/src/branch/main/config.ini.example '
              f'change to your needs and run again!')
        exit(1)
    config = configparser.ConfigParser()
    config.read(config_path)

    torrent_temp_dir = config['default']['torrent_temp_dir']
    qbittorrent_upload_dir = config['default']['qbittorrent_upload_dir']
    qbittorrent_watch_dir = config['default']['qbittorrent_watch_dir']
    static_tags = config['default']['static_tags'].split()
    delayed_seed = config['default'].getboolean('delayed_seed')
    use_hardlinks = config['default'].getboolean('use_hardlinks', fallback=False)
    use_torznab = config['default'].getboolean('use_torznab', fallback=False)
    torznab_poll_interval = config['default'].getint('torznab_poll_interval', fallback=30)

    if(torznab_poll_interval < 1):
        print('torznab_poll_interval must be greater than 0')
        exit(2)

    chevereto_api_key = config['imagehost:chevereto']['api_key']
    chevereto_host = config['imagehost:chevereto']['host']

    # qBittorrent API configuration
    if config.has_section('client:qbittorrent'):
        use_qb_api = config['client:qbittorrent'].getboolean('use_api', fallback=False)
        qb_url = config['client:qbittorrent'].get('url', fallback=None)
        qb_category = config['client:qbittorrent'].get('category', fallback="Upload")
    else:
        use_qb_api, qb_url, qb_category = None, None, None
    if use_qb_api:
        if not qb_url:
            print("Error: use_qbittorrent_api is enabled, but qbittorrent_url is not set in the config.")
            exit(2)

        qbt_client = qbittorrent_client.QBittorrentClient(qb_url)

    chevereto_api_key = config['imagehost:chevereto']['api_key']
    chevereto_host = config['imagehost:chevereto']['host']

    # qBittorrent API configuration
    if config.has_section('client:qbittorrent'):
        use_qb_api = config['client:qbittorrent'].getboolean('use_api', fallback=False)
        qb_url = config['client:qbittorrent'].get('url', fallback=None)
        qb_category = config['client:qbittorrent'].get('category', fallback="Upload")
    else:
        use_qb_api, qb_url, qb_category = None, None, None
    if use_qb_api:
        if not qb_url:
            print("Error: use_qbittorrent_api is enabled, but qbittorrent_url is not set in the config.")
            exit(2)

        qbt_client = qbittorrent_client.QBittorrentClient(qb_url)

    # Read Tracker from config sections
    tracker_sections = [s for s in config.sections()
                        if s.startswith('tracker:')]

    trackers = [
        Tracker(announce_url=config[s]['announce_url'],
                category=config[s].get('category'),
                source_tag=config[s]['source_tag'],
                torznab_url=config[s]['torznab_url']
                ) for s in tracker_sections
    ]
    print(trackers)

    video_path = args.video if args.video else input("Video Path: ")
    video_basename = basename(video_path)
    video_clipname = splitext(video_basename)[0]
    print(f'https://www.clips4sale.com/clips/search/{quote(video_clipname)}/category/0/storesPage/1/clipsPage/1')
    c4s_url = args.url if args.url else input("C4S Url: ")

    if not isfile(video_path):
        print('Video file does not exists: ', video_path)
        exit(2)

    clip = extract_clip_data(c4s_url)
    print(clip)

    target_dir = qbittorrent_upload_dir + f'{clip.studio} - {clip.title}'

    # Create dir structure
    makedirs(target_dir + '/images')

    target_file_path = f'{target_dir}/{clip.studio} - {clip.title}{splitext(video_path)[1]}'

    # Create hardlink or symlink to video file in upload dir
    if use_hardlinks:
        print(f"Creating hardlink: {target_file_path}")
        link(src=video_path, dst=target_file_path)
    else:
        print(f"Creating symlink: {target_file_path}")
        symlink(src=video_path, dst=target_file_path)

    # Download Header Image from C4S
    r = requests.get(clip.image_url)
    r.raise_for_status()
    with open(target_dir + '/images/header.jpg', 'wb') as header:
        header.write(r.content)

    # Upload header image
    header_image_link = chevereto_image_upload(target_dir + '/images/header.jpg', chevereto_host=chevereto_host, chevereto_api_key=chevereto_api_key)

    # Create Thumbnail Image (using default vcsi parameters copied from interactive debug run)
    vcsi_args = argparse.Namespace(output_path=target_dir + '/images/thumbnail.jpg', config=None,
                              start_delay_percent=7,
                              end_delay_percent=7, delay_percent=None, grid_spacing=None, grid_horizontal_spacing=5,
                              grid_vertical_spacing=5, vcs_width=1500, grid=vcsi.Grid(x=4, y=4), num_samples=None,
                              show_timestamp=True, metadata_font_size=16,
                              metadata_font=get_font_path() + '/DejaVuSans-Bold.ttf', timestamp_font_size=12,
                              timestamp_font=get_font_path() + '/DejaVuSans.ttf', metadata_position='top',
                              background_color=vcsi.Color(r=0, g=0, b=0, a=255),
                              metadata_font_color=vcsi.Color(r=255, g=255, b=255, a=255),
                              timestamp_font_color=vcsi.Color(r=255, g=255, b=255, a=255),
                              timestamp_background_color=vcsi.Color(r=0, g=0, b=0, a=170),
                              timestamp_border_color=vcsi.Color(r=0, g=0, b=0, a=255), metadata_template_path=None,
                              manual_timestamps=None, is_verbose=False, is_accurate=False, accurate_delay_seconds=1,
                              metadata_margin=10, metadata_horizontal_margin=10, metadata_vertical_margin=10,
                              timestamp_horizontal_padding=3, timestamp_vertical_padding=3,
                              timestamp_horizontal_margin=5, timestamp_vertical_margin=5, image_quality=100,
                              image_format='jpg', recursive=False, timestamp_border_mode=False,
                              timestamp_border_size=1,
                              capture_alpha=255, list_template_attributes=False, frame_type=None, interval=None,
                              ignore_errors=False, no_overwrite=False, exclude_extensions=[], fast=False,
                              thumbnail_output_path=None, actual_size=False, timestamp_format='{TIME}',
                              timestamp_position=vcsi.TimestampPosition.se)
    vcsi.process_file(f'{target_dir}/{clip.studio} - {clip.title}{splitext(video_path)[1]}', args=vcsi_args)
    thumbnail_image_link = chevereto_image_upload(target_dir + '/images/thumbnail.jpg', chevereto_host=chevereto_host, chevereto_api_key=chevereto_api_key)

    script_dir = Path(__file__).resolve().parent
    template_dir = script_dir / 'templates'

    jinja_env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True)

    # Create Torrents
    for tracker in trackers:
        t = Torrent(path=target_dir,
                    trackers=[tracker.announce_url],
                    )
        t.private = True
        t.source = tracker.source_tag
        t._metainfo['metadata'] = dict()
        t._metainfo['metadata']['title'] = f'{clip.studio} - {clip.title}'
        # TODO: category is not working, this is probably unsupported on luminance currently?
        t._metainfo['metadata']['category'] = tracker.category
        t._metainfo['metadata']['cover url'] = header_image_link
        t._metainfo['metadata']['taglist'] = format_tags_with_dots(clip.keywords + static_tags)
        template = jinja_env.get_template('default_bbcode.jinja')
        t._metainfo['metadata']['description'] = template.render(
            clip=clip,
            header_image_link=header_image_link,
            thumbnail_image_link=thumbnail_image_link,
        )
        print("BBCode:\n-----TORRENT DESCRIPTION-----\n" +
              t._metainfo['metadata']['description'] + "\n-----DESCRIPTION END-----\n")

        print(f'creating torrent for {tracker.source_tag}... {t}')
        t.generate(callback=print_torrent_hash_process, interval=1)
        t.write(f'{torrent_temp_dir}[{tracker.source_tag}]{clip.studio} - {clip.title}.torrent')
        print(f'Torrent created in: {torrent_temp_dir}')
        torrent_title = f'{clip.studio} - {clip.title}'
        
        if use_torznab:
            try:
                print(f'[{tracker.source_tag}] Checking for existing torrents...')
                existing_url = torznab.poll_for_torrent(tracker.source_tag, tracker.torznab_url, torrent_title, 0, 1)
                if existing_url:
                    print(f'[{tracker.source_tag}] Torrent already exists on tracker, skipping upload.')
                    continue
            except TimeoutError:
                print(f'[{tracker.source_tag}] No existing torrents found.')
            except Exception as e:
                print(f'[{tracker.source_tag}] Error while polling for existing torrent: {e}')
                exit(4)
            
            print(f'[{tracker.source_tag}] Upload torrent to tracker, then wait for it to be indexed...')
            try:
                torrent_url = torznab.poll_for_torrent(tracker.source_tag, tracker.torznab_url, torrent_title, torznab_poll_interval)
                print(f'[{tracker.source_tag}] Found torrent on tracker: {torrent_url}')
            except Exception as e:
                print(f'Error while polling for torrent: {e}')
                exit(4)
        elif delayed_seed:
            if args.delay_seconds:
                print(f'Upload torrent to tracker {tracker.source_tag}. Waiting {args.delay_seconds} seconds before autoloading to qBittorrent...')
                time.sleep(args.delay_seconds)
            else:
                input(f'Upload torrent to tracker {tracker.source_tag}, then hit Enter to autoload to qBittorrent...')

        torrent_filename = f'[{tracker.source_tag}]{clip.studio} - {clip.title}.torrent'
        torrent_path = f'{torrent_temp_dir}{torrent_filename}'

        if use_qb_api:
            print(f"Uploading {torrent_filename} via qBittorrent API...")
            torrent_name = f'{clip.studio} - {clip.title}'
            try:
                with open(torrent_path, 'rb') as f:
                    torrent_bytes = f.read()
                qbt_client.send_torrent(
                    torrent_bytes=torrent_bytes,
                    name=torrent_name,
                    category=qb_category,
                    savepath=qbittorrent_upload_dir,
                )
                print("API Upload successful.")
                # Clean up the temporary torrent file after successful upload
                try:
                    os.remove(torrent_path)
                except OSError as e:
                    print(f"Error removing temp torrent {torrent_path}: {e}")
            except Exception as e:
                print("API upload failed:", e)
                exit(3)
        else:
            watch_target = f'{qbittorrent_watch_dir}{torrent_filename}'
            print(f"Using watch folder: {watch_target}")
            move(torrent_path, watch_target)

        print('done...')


if __name__ == "__main__":
    main()
