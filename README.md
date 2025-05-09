# clips2share

[![Primary Repo](https://img.shields.io/badge/Primary%20Repo-Codeberg-blue?logo=codeberg)](https://codeberg.org/c2s/clips2share)

> 📦 This is a GitHub mirror of the [original clips2share repository on Codeberg](https://codeberg.org/c2s/clips2share).
>
> Please [file issues](https://codeberg.org/c2s/clips2share/issues) and [submit pull requests](https://codeberg.org/c2s/clips2share/pulls) **on Codeberg, not here**.


Clips2share helps you with the process of creating torrents for uploading adult clips to your favorite torrent tracker:

- extract all metadata from a user provided clips4sale link (title, description, tags, price, clip quality, and more)
- embed all these data using a template in the torrents metadata
- download header image from clips4sale and upload to an image hoster 
- create thumbnails from local clip using vcsi library and upload to image hoster 
- create the final torrent with torf lib and send it to qbittorrent 
- allows uploading to multiple trackers


## Installation

Install clips2share with pip

```bash
pip install clips2share
```

And make sure that ffmpeg is installed, then run clips2share from commandline:

```bash
clips2share
```

The first run will tell you to download and install the config.ini to your 'user_config_dir'. 


## Running in Docker

You can run clips2share without installing it locally using Docker:

```bash
docker run --pull always --rm --user $(id -u):$(id -g) \
  -v /mypath/config:/config \
  -v /mypath/torrent:/torrent \
  noired4/clips2share:latest \
  --video "/torrent/Upload/video.mp4" \
  --url "https://www.example.com" \
  --delay-seconds 120
```
This runs the app in a temporary container, mounts your configuration and video folders, and passes the necessary arguments. The container will automatically remove itself when the task is complete.

### Notes
- The '/config' volume should contain a config.ini file. You can use the example provided in the Configuration section.
- The '/data' volume should point to a directory containing the video file you want to upload.
- If you use qBittorrent with watch folders, ensure that the 'qbittorrent_watch_dir' path in config.ini is mapped inside '/data' so the generated .torrent file appears in the expected location inside the container.
- **Important:** Make sure that the path mappings used by your qBittorrent container match those used by clips2share. For example, if both containers access your host's '/home/user/data' as '/data', the paths will align correctly. If they don’t match, torrent files may reference incorrect locations, causing qBittorrent to fail seeding.
- **Also important:** The 'torrent_temp_dir' setting must point to a directory that exists inside a Docker-mounted volume. This ensures that the resulting .torrent file is accessible on your host system, allowing you to upload it to a tracker or inspect it if needed.


## Configuration

This is an example config.ini

```ini
[default]
torrent_temp_dir = /home/user/qBittorrent/
qbittorrent_upload_dir = /home/user/qBittorrent/Uploads/
qbittorrent_watch_dir = /home/user/qBittorrent/Uploads/_autoadd/
static_tags = clips4sale.com
delayed_seed = True
use_hardlinks = True

[imagehost:chevereto]
api_key = chv_T_your_api_key_check_your_user_settings_after_logging_in
host = hamster.is

[client:qbittorrent]
use_api = False
url = http://user:pass@127.0.0.1:8080
category = Upload

[tracker:empornium]
announce_url = http://tracker.empornium.sx:2710/YOURPASSKEY/announce
source_tag = Emp
category = Straight
```

| Default Settings       | Description                                                                                     |
|------------------------|-------------------------------------------------------------------------------------------------|
| torrent_temp_dir       | Directory where the torrent is placed, ready to be uploaded to the tracker                      |
| qbittorrent_upload_dir | Directory where the upload files are created                                                    |
| qbittorrent_watch_dir  | Directory where the torrent is moved to get automatically seeded                                |
| static_tags            | Tags to be added to every torrent                                                               |
| delayed_seed           | If true, wait for user input and delay seed to prevent announcing an unknown torrent to tracker |
| use_hardlinks          | If true, creates hard links instead of symlinks for the video file                              |

| Chevereto | Description                                                                                                                         |
|-----------|-------------------------------------------------------------------------------------------------------------------------------------|
| host      | Hostname of the Chevereto image hoster                                                                                              |
| api_key   | API Key for the Chevereto image hoster. After registering and logging in to your account, you will find it in your profile settings |

Note: Chevereto is the image hosting software used by EMP. To use it, you need to create an account [here](https://hamster.is/) and generate an API key in your user profile.

| Client Settings  | Description                                      |
|------------------|--------------------------------------------------|
| use_api          | If true, uses client API instead of watch folders|
| url              | URL for the client with username and password    |
| category         | Client specific category to assign the torrent   |

| Tracker Settings | Description                                      |
|------------------|--------------------------------------------------|
| announce_url     | Tracker announce url                             |
| source_tag       | Tracker specific source tag added to the torrent |
| category         | Tracker specific category, added as tag          |


## Usage/Examples
Example usage below (user wants to upload /tmp/my_video.mp4 and needs to provide only the path to local clip and the c4s link):

```bash
clips2share

[Tracker(announce_url='http://tracker.empornium.sx:2710/yourpasskey/announce', category='Straight', source_tag='Emp')]

Video Path: /tmp/my_video.mp4

https://www.clips4sale.com/clips/search/my_video/category/0/storesPage/1/clipsPage/1

C4S Url: https://www.clips4sale.com/studio/12345/54321/my-video-1080p

C4SData(title='My Video 1080p', studio='C4S Studio', price='$14.99 USD', date='3/1/25 1:23 AM', duration='15 min', size='1693 MB', format='mp4', resolution='1080p', description='The C4S Clip Description', category='POV', related_categories=['Glove', 'Leather Gloves', 'Play'], keywords=['Straight', 'POV'], url='https://www.clips4sale.com/studio/12345/54321/my-video-1080p', image_url='https://imagecdn.clips4sale.com/accounts123/54321/clip_images/previewlg_12345.jpg')
Processing /tmp/my_video.mp4...
Sampling... 16/16
Composing contact sheet...
Cleaning up temporary files...
creating torrent for Emp... Torrent(path=PosixPath('/tmp/upload/my_video'), name='My Video 1080p', trackers=[['http://tracker.empornium.sx:2710/yourpasskey/announce']], private=True, source='Emp', piece_size=2097152)
[/tmp/upload/my_video]   0 % done
[/tmp/upload/my_video] 100 % done
upload torrent to tracker Emp, than hit enter to autoload to qBittorrent...
```

## Command-line Options

You can skip interactive prompts by using the following command-line arguments:

| Short | Long            | Type | Description                                                                   |
|-------|-----------------|------|-------------------------------------------------------------------------------|
| -V    | --video         | Path | Path to the local video file                                                  |
| -u    | --url           | URL  | Clip Store URL                                                                |
| -D    | --delay-seconds | Int  | Delay (in seconds) before autoloading the torrent when `delayed_seed` is true |

### Example:
```bash
clips2share -V "/tmp/my_video.mp4" -u "https://www.clips4sale.com/studio/12345/54321/my-video-1080p" -D 300
```

## Environment Variables

This optional environment variable allows to overwrite the path to the config (will be preferred instead of the user_config_dir)

`C2S_CONFIG_PATH`: `/path/to/config.ini`


## Contributing

Contributions are always welcome!


## Contact

For feedback, feature requests or bug reports please create an issue or join our [discord developer channel](https://discord.gg/45beWDKq)


## License

[MIT](https://choosealicense.com/licenses/mit/)

