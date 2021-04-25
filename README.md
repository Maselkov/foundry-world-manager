# Foundry World Manager
A Python-based tool that helps manage [FoundryVTT](https://foundryvtt.com/) Worlds.
The main functionality implemented thus far is to compress all of a World's PNG and
JPEG images to WEBP. The tool also helps with deduplication of image files.

# Warning

Ensure that you have a backup before running this tool.
Do not run the tool while your world is running.

# Pre-requisites
## Python 3.9

```bash
 python3 -m pip install -r requirements.txt
```

## FFMPEG
Lastly, you will also need to have access to [FFMPEG](https://www.ffmpeg.org/download.html).
I personally use the version recommended by Audacity, which can be downloaded
[here](https://lame.buanzo.org/#lamewindl).

# Compatibility

## Operating Systems
Currently, the tool has only been tested on Windows and Linux systems.

## Foundry
The tool has only been tested on Worlds built for Foundry 0.7.9. If you have
Worlds built for any other version, please use the tool at your own risk.

# Instructions
Regardless of how you use this tool, the first step is to download it from
Github and extract it to an empty folder.

## Using the tool from the command prompt
If you just want to compress your world's PNGs and JPEGs to WEBP, you can simply
pass the main arguments to the program via command line. Here is a full example
of how to do so. First, boot up your command prompt. Then, navigate to the folder
where you extracted the tool by typing the following:
```
> cd "/path/to/the/tool"
```
Finally, type the following (making the appropriate substitutions, of course)

### __For Windows users__
```
> python fwm.py -u "C:/Users/jegasus/AppData/Local/FoundryVTT/Data" -w "worlds/porvenir" -c "C:/Program Files/FoundryVTT/resources/app/public" -f "C:/Program Files/ffmpeg/ffmpeg.exe" -d y
```
### __For Linux users__
```
> python fwm.py -u "/home/jegasus/foundrydata/Data" -w "worlds/porvenir" -c "/home/jegasus/foundryvtt/resources/app/public" -f "/usr/bin/ffmpeg" -d y
```
The main flags above are explained below:

- `-u` or `--user-data-folder`: Foundry User Data folder. Ex: "C:/Users/jegasus/AppData/Local/FoundryVTT/Data" or "/home/jegasus/foundrydata/Data"
- `-w` or `--world-folder`: Foundry World folder. Ex: "worlds/kobold-cauldron", "worlds/porvenir"
- `-c` or `--core-data-folder`: Foundry Core folder. Ex: "C:/Program Files/FoundryVTT/resources/app/public" or "/home/jegasus/foundryvtt/resources/app/public"
- `-f` or `--ffmpeg-location`: Location of the FFMPEG application/executable. Ex: "C:/Program Files/ffmpeg/ffmpeg.exe" or "/usr/bin/ffmpeg"
- `-d` or `--delete-unreferenced-images`: Flag that determines whether or not to delete unreferenced images. Should be "y" or "n".

When making the appropriate substitutions, make sure you point to the correct
files and folders on your disk.

## Using this tool inside an interactive Python session
If you prefer, you can use this tool interactively to gain access to the tool's
internal functions and have more control over what the tool actually does. To do
so, initiate a Python session and paste the following chunk of code (making the
appropriate substitutions, of course):

```python
import sys

# Path to the folder that contains the jegasus_world_manager.py file
world_manager_location = "C:/path/to/folder/with/tool"
sys.path.append(world_manager_location)

# Importing the tool
import jegasus_world_manager as jwm

# Defining the main file & folder paths
user_data_folder = r'C:\Users\jegasus\AppData\Local\FoundryVTT\Data'
world_folder = r'worlds\porvenir'
core_data_folder = r'C:\Program Files\FoundryVTT\resources\app\public'
ffmpeg_location = r'C:\Program Files (x86)\Audacity\libraries\ffmpeg.exe'

# Creating an instance of the `world_ref` object, which you can
# use however you want
my_world_refs = jwm.world_refs(
  user_data_folder=user_data_folder,
  world_folder=world_folder,
  core_data_folder=core_data_folder,
  ffmpeg_location=ffmpeg_location)

```
For an explanation of what the main arguments above represent, just look at the previous section.
