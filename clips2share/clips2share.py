# Support for direct script execution
# This is a workaround for running the script directly without installing it as a package.
if __name__ == "__main__" and __package__ is None:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

# End of workaround

import argparse
import tomllib
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
from pathlib import Path

@dataclass
class Tracker:
    name: str
    announce_url: str
    category: str
    source_tag: str

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

def fapping_empornium_image_upload(img_path):
    """
    Uploads an image to fapping.empornium.sx and returns the image url on success
    """
    r = requests.post('https://fapping.empornium.sx/upload.php', files=dict(ImageUp=open(img_path, 'rb')))
    r.raise_for_status()
    image_id = r.json()['image_id_public']
    image_url = f'https://fapping.empornium.sx/image/{image_id}'
    image = requests.get(image_url)
    soup = BeautifulSoup(image.text, 'html.parser')
    return soup.select_one('input[id^="direct-link"]').get('value')

def format_tags_with_dots(source_list):
    return [s.replace(' ', '.') for s in source_list]

def print_torrent_hash_process(torrent, filepath, pieces_done, pieces_total):
    print(f'[{filepath}] {pieces_done/pieces_total*100:3.0f} % done')

def get_font_path():
    return str(files('clips2share') / 'fonts')

def has_nested_key(d, *keys):
    for key in keys:
        if key not in d:
            return False
        d = d[key]
    return True

def parse_arguments():
    parser = argparse.ArgumentParser(description="clips2share CLI")
    parser.add_argument('-V', '--video', type=str, help="Path to the video file")
    parser.add_argument('-u', '--url', type=str, help="Clip Store URL")
    parser.add_argument('-D', '--delay-seconds', type=int, help="Auto-continue delay in seconds after torrent is created")
    return parser.parse_args()

def main():
    args = parse_arguments()
    config_path = getenv('C2S_CONFIG_PATH') if getenv('C2S_CONFIG_PATH') else user_config_dir(appname='clips2share') + '/config.toml'
    if not isfile(config_path):
        print(f'config_path {config_path} does not exist, download example config here: '
              f'https://codeberg.org/c2s/clips2share/src/branch/main/config.toml.example '
              f'change to your needs and run again!')
        exit(1)
    with open(config_path, 'rb') as f:
        config = tomllib.load(f)

    torrent_temp_dir = config['torrent']['temporary_directory']
    upload_dir = config['tracker']['upload_directory']
    qbittorrent_watch_dir = config['client']['qbittorrent']['watch_directory']
    static_tags = config['tracker']['static_tags']
    delayed_seed = config['default']['delayed_seed']
    use_hardlinks = config['default'].get('use_hardlinks', False)  # Default to False if not present

    # qBittorrent API configuration
    if has_nested_key(config, 'client', 'qbittorrent'):
        use_qb_api = config['client']['qbittorrent']['use_api']
        qb_url = config['client']['qbittorrent']['url']
        qb_category = config['client']['qbittorrent']['category']
    else:
        use_qb_api, qb_url, qb_category = None, None, None
    if use_qb_api:
        if not qb_url:
            print("Error: use_qbittorrent_api is enabled, but qbittorrent_url is not set in the config.")
            exit(2)

        qbt_client = qbittorrent_client.QBittorrentClient(qb_url)

    # Read Trackers from config sections
    tracker_config = config.get('tracker', {})
    tracker_sections = {
        name: section
        for name, section in tracker_config.items()
        if isinstance(section, dict)
    }

    trackers = [
        Tracker(
            name=name,
            announce_url=section['announce_url'],
            category=section.get('category'),
            source_tag=section['source_tag']
        )
        for name, section in tracker_sections.items()
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

    target_dir = upload_dir + f'{clip.studio} - {clip.title}'

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
    header_image_link = fapping_empornium_image_upload(target_dir + '/images/header.jpg')

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
    thumbnail_image_link = fapping_empornium_image_upload(target_dir + '/images/thumbnail.jpg')

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
        if delayed_seed:
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
                    savepath=upload_dir,
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
