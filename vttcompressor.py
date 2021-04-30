import hashlib
import imghdr
import json
import mimetypes
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import warnings
import urllib.parse

from bs4 import BeautifulSoup

# Command used to supress multiple warnings about trying to parse regular
# strings as HTML chunks.
warnings.filterwarnings('ignore')


def dict_walker(in_dict, pre=None):
    '''
    Function that walks through an indefinitely complex dictionary (can contain
    lists, tuples or other dictionaries), and iterates through all of the
    dictionary's "leaves". This works as an iterator that returns a big list
    that contains the full "address" of a leaf.

    Modified from https://stackoverflow.com/a/12507546/8667016

    INPUTS:
    -------
    in_dict (DICT) : A dictionary of arbitrary depth/complexity.

    RETURNS:
    --------
    iterated_output (LIST) : A list that contains the full address of the leaf
        in the dictionary.

    EXAMPLE:
    --------
    # Input:
    my_dict = {'part_1':[5,6,7],
               'part_2':[3,6,{'a':999,
                              'b':777,
                              'c':123}]}

    for this_full_address in dict_walker(in_dict=my_dict):
        print(this_full_address)

    # Output:
    # ['part_1', 0, 5]
    # ['part_1', 1, 6]
    # ['part_1', 2, 7]
    # ['part_2', 0, 3]
    # ['part_2', 1, 6]
    # ['part_2', 2, 'a', 999]
    # ['part_2', 2, 'b', 777]
    # ['part_2', 2, 'c', 123]
    '''

    pre = pre[:] if pre else []
    if isinstance(in_dict, dict):
        for key, value in in_dict.items():
            if isinstance(value, dict):
                for d in dict_walker(value, pre + [key]):
                    yield d
            elif isinstance(value, list) or isinstance(value, tuple):
                for i, v in enumerate(value):
                    for d in dict_walker(v, pre + [key, i]):
                        yield d
            else:
                yield pre + [key, value]
    else:
        yield pre + [in_dict]


def get_nested_dict_recursive(in_dict, dict_address):
    '''
    Function that allows you to access a specific "address" inside an
    arbitrarily-complex dictionary.

    INPUTS:
    -------
    in_dict (DICT) : Dictionary to be read.
    dict_address (LIST) : Address of the object being requested.

    RETURNS:
    --------
    output (any) : The output of this function is the actual item at the
        "address" inside the input dictionary.


    EXAMPLE:
    --------
    # Input:
    my_dict = {'part_1':[5,6,7],
               'part_2':[3,6,{'a':999,
                              'b':777,
                              'c':123}]}

    address_1 = ['part_1', 2]
    address_2 = ['part_2', 2]

    print(get_nested_dict_recursive(in_dict=my_dict, dict_address=address_1))
    print(get_nested_dict_recursive(in_dict=my_dict, dict_address=address_2))

    # Output:
    # 7
    # {'a': 999, 'b': 777, 'c': 123}
    '''
    if len(dict_address) == 1:
        return in_dict[dict_address[0]]
    else:
        return get_nested_dict_recursive(in_dict[dict_address[0]],
                                         dict_address[1:])


def edit_nested_dict_recursive(in_dict, dict_address, new_value):
    '''
    Function that allows you to edit a specific "address" inside an
    arbitrarily-complex dictionary and assign a new value/object to it.

    INPUTS:
    -------
    in_dict (DICT) : Dictionary to be read.
    dict_address (LIST) : Address of the object that will receive `new_value`.
    new_value (any) : New value to be stored in the input dictionary's "address".

    RETURNS:
    --------
    None

    EXAMPLE:
    --------
    # Input:
    my_dict = {'part_1':[5,6,7],
               'part_2':[3,6,{'a':999,
                              'b':777,
                              'c':123}]}

    my_address = ['part_1', 2]
    my_new_value = 'DOG'

    edit_nested_dict_recursive(my_dict, my_address, my_new_value)

    print(my_dict)

    # Output:
    # {'part_1': [5, 6, 'DOG'],
    #  'part_2': [3, 6, {'a': 999,
    #                    'b': 777,
    #                    'c': 123}]}
    '''
    if len(dict_address) == 1:
        in_dict[dict_address[0]] = new_value
    else:
        edit_nested_dict_recursive(in_dict[dict_address[0]], dict_address[1:],
                                   new_value)


class ImageReference:
    '''
    Class that encapsules one single image reference inside the Foundry world.
    This class contains several helpful methods and attributes that make it easy
    to understand the image reference.
    Mainly, the `ImgRef` object contains information about where this image
    reference is located in the world.
    For example, if there is a journal entry that makes a reference to
    "worlds/porvenir/handouts/ScytheOfTheHeadlessHorseman.webp", an `img_ref`
    instance can be created to indicate exactly where in the world folder this
    reference can be found: inside the 4th line of the "worlds/myworld/data/journal.db"
    file, at the following "address": ['img', 'worlds/porvenir/handouts/ScytheOfTheHeadlessHorseman.webp'].
    Among many other things, this object also includes an attribute that indicates
    the image's filetype/extension (JPG, PNG, WEBP), and an attribute that helps
    determine whether the image was actually encoded using its filename's
    extension's protocols.

    Main attributes:
        Attributes that never change:
        -----------------------------
        self.world_folder (Path) : Directory path of the current world
        self.core_data_folder (Path) : Directory path of the Foundry installation
        self.ref_path (Path) : Indicates the filepath to the file that contains
            this image reference. For example, if an image reference is made
            inside the world's "journal.db" file, the `ref_file_path` would be
            something like "worlds/myworld/data/journal.db"
        self.ref_file_type (STR) : Type of file in which this reference was found.
            Can be either "json" or "db".
        self.ref_file_line (INT or None): For '.db' reference files, there are multiple
            JSON-like dictionaries per row. The `ref_file_line` argument indicates
            which line in the ".db" file this particular `img_ref` can be found.
            For example, if the reference to the image is on the 5th line of the
            "journal.db" file, then `ref_file_line` will equal 4. In cases where
            the reference was found in a ".json" file, this attribute is instead
            set to None.
            NOTE: As with everything else in Python, this line number is zero-indexed.
        self.json_address (LIST) : Full "address" of the reference inside the "db"
            or "json" file.
        self.world_ref (WorldRefs) : Object that "owns"
            this reference. This is a collection of `img_ref`s.
        self.img_ref_content_is_html (BOOL) : Indicates whether this reference is
            just a simple STRING or if it's an HTML chunk.

        Attributes that are mutable:
        ----------------------------
        self.ref_img_in_world_folder (BOOL) : Indicates whether or not this
            reference tries to point to an image file on disk that is inside
            the world folder.
        self.img_path_on_disk (STR) : File path on disk to which this reference
            points. The difference between this and the `ref_file_path` attribute
            is that if the image being referenced is inside the Foundry Core folder,
            the `img_path_on_disk` attribute will have the full absolute path to
            the image on disk. The `ref_file_path` attibute, however, will only have
            the "stem" of the path (i.e., the image path relative to the Foundry
            Core folder).
            Furthermore, in cases where the image does not exist on disk, the
            `the img_path_on_disk` attribute is set to an error value.
        self.img_exists (BOOL) : Indicates whether or not this file actually exists
            on disk
        self.img_encoding (STR) : Type of encoding used for the image. Expected
            values can be "png", "jpeg" or "webp".
        self.correct_extension (BOOL) : Indicates whether or not the encoding
            actually matches the file extension. For example, if a file is named
            "my_img.jpeg", but it was encoded using "png", the `correct_extension`
            attribute will be False.
        self.img_hash (STR) : Hash of the image file on disk. Used for de-duplication.
        self.is_webp (BOOL) : Indicates whether or not the file extension is ".webp"
        self.webp_ref_path (STR) : File path for the ".webp" version of
            this image (regardless of whether or not the ".webp" version exists).
        self.webp_copy_exists (BOOL) : Indicates whether or not the ".webp" version
            of this image exists on disk
        self.img_ref_external_web_link (BOOL) : Indicates whether or not this
            image reference is actually a hyperlink to an external file on
            the web.
    '''
    def __init__(self,
                 ref_file_type=None,
                 ref_file_path=None,
                 ref_file_line=None,
                 full_json_address=None,
                 ref_path=None,
                 WorldRefs_obj=None):
        '''
        Function used to instantiate new objects from the `img_ref` class.

        INPUTS:
        -------
        ref_file_type (STR) Indicates the file type of the location where this
            image reference is stored. Can only take two values: 'json' or 'db'.
        ref_file_path (STR) : Indicates the filepath to the file that contains
            this image reference. For example, if an image reference is made
            inside the world's "journal.db" file, the `ref_file_path` would be
            something like "worlds/myworld/data/journal.db"
        ref_file_line (INT or None): For '.db' reference files, there are multiple
            JSON-like dictionaries per row. The `ref_file_line` argument indicates
            which line in the ".db" file this particular `img_ref` can be found.
            For example, if the reference to the image is on the 5th line of the
            "journal.db" file, then `ref_file_line` will equal 4. In cases where
            the reference was found in a ".json" file, this attribute is instead
            set to None.
            NOTE: As with everything else in Python, this line number is zero-indexed.
        full_json_address (LIST) : Full "address" of an image's reference inside
            the complex JSON dictionary.
        ref_path (Path) : Actual disk location/filepath of the image being
            referenced. Ex: "worlds/porvenir/handouts/ScytheOfTheHeadlessHorseman.webp"
        WorldRefs_obj (OBJECT) : This is an instance of the `WorldRefs` object
            (defined below). The `WorldRefs_obj` attribute points to the `WorldRefs`
            object to which this `img_ref` belongs, and inside of which all other
            image references can be found.
        ref_id (STR) : Unique string that can be used to identify each individual
            `img_ref` object

        RETURNS:
        --------
        img_ref (OBJECT) : The newly created `img_ref` object itself.

        EXAMPLE:
        --------
        # Input:
        my_ref = img_ref(ref_file_type='db',
                         ref_file_path='worlds/myworld/data/journal.db',
                         ref_file_line=4,
                         full_json_address=['img', 'worlds/porvenir/handouts/ScytheOfTheHeadlessHorseman.webp'],
                         ref_path='worlds/porvenir/handouts/ScytheOfTheHeadlessHorseman.webp',
                         WorldRefs_obj=my_WorldRefs)

        # Output:
        # None
        '''

        # Setting attributes that will never be updated
        self.world_folder = WorldRefs_obj.world_folder
        self.core_data_folder = WorldRefs_obj.core_data_folder
        self.ref_file_path = ref_file_path
        self.ref_file_type = ref_file_type
        self.ref_file_line = ref_file_line
        self.json_address = full_json_address[:-1]
        self.world_ref = WorldRefs_obj
        self.img_hash = None
        self.is_webp = False
        self.file_reference = self.world_ref.files[self.ref_file_type][
            self.ref_file_path]
        if self.ref_file_type == 'db':
            self.file_reference = self.file_reference[self.ref_file_line]
        string_to_hash = (self.world_folder / self.core_data_folder /
                          self.ref_file_path / self.ref_file_type /
                          str(self.ref_file_line) / str(self.json_address) /
                          'img_ref')

        self.ref_id = hashlib.sha256(str(string_to_hash).encode()).hexdigest()

        # Looks into the actual content of the reference. Sometimes it is just
        # a string with the filepath to the image. Other times it is a chunk of
        # HTML that links to an embedded image. In any case, this content needs
        # to be investigated to generate a bunch of the `img_ref`'s attributes.
        img_ref_content = full_json_address[-1]

        # Checking if the content of the reference is an HTML chunk.
        self.img_ref_content_is_html = True if BeautifulSoup(
            img_ref_content, 'html.parser').find() else False

        # Setting the attributes that might be edited later.
        self.set_editable_attributes(Path(ref_path))

    def get_img_ref_content(self):
        '''
        Retrieves this `ImageRefeference`'s content from the main world reference object

        INPUTS:
        -------
        None

        RETURNS:
        --------
        img_ref_content (STR) : The actual content of the reference. Sometimes
            it is just a string with the filepath to the image. Other times it
            is a chunk of HTML that links to an embedded image.

        EXAMPLE:
        --------
        # Input:
        print(my_ref.get_img_ref_content())

        # Output:
        # 'worlds/porvenir/handouts/ScytheOfTheHeadlessHorseman.webp'
        '''
        content = get_nested_dict_recursive(self.file_reference,
                                            self.json_address)
        return content

    def set_editable_attributes(self, ref_path=None):
        '''
        This is where several of the `img_ref`'s helper attributes get initially
        set, such as the attribute that determines whether the image was actually
        encoded using its filename's extension's protocols.

        INPUTS:
        -------
        ref_path (STR) : Actual disk location/filepath of the image
            being referenced. Ex: "worlds/porvenir/handouts/ScytheOfTheHeadlessHorseman.webp"

        RETURNS:
        --------
        None

        EXAMPLE:
        --------
        # Input:
        my_ref_path = my_ref.full_json_address[:-1]

        my_img_ref.set_editable_attributes(my_ref_path)

        '''

        self.ref_path = ref_path

        self.ref_img_in_world_folder = self.world_folder in ref_path.parents

        if self.ref_path.is_file():
            self.img_path_on_disk = self.ref_path
            self.img_exists = True
        elif (p := Path(self.core_data_folder / self.ref_path)).is_file():
            self.img_path_on_disk = p
            self.img_exists = True
        else:
            path = Path(urllib.parse.unquote(str(self.ref_path)))
            if path.is_file():
                self.img_path_on_disk = path
                self.img_exists = True
            else:
                self.img_path_on_disk = None
                self.img_exists = False
                self.img_encoding = None
        if self.img_exists:
            img_encoding_imghdr = imghdr.what(self.img_path_on_disk)

            img_encoding_mime_temp = mimetypes.guess_type(
                self.img_path_on_disk)[0]
            img_encoding_mime = img_encoding_mime_temp.split(
                '/')[1].lower() if img_encoding_mime_temp is not None else None

            if img_encoding_imghdr:
                self.img_encoding = img_encoding_imghdr
            elif img_encoding_mime:
                self.img_encoding = img_encoding_mime
            else:
                self.img_encoding = None
            self.img_hash = hashlib.md5(
                open(self.img_path_on_disk, 'rb').read()).hexdigest() if (
                    self.img_exists and self.ref_img_in_world_folder) else None
            self.is_webp = Path(self.ref_path).suffix.lower() == '.webp'
            rename_images = True
            if rename_images:
                stem = Path(self.img_path_on_disk).stem.replace(" ",
                                                                "-").lower()
                stem = re.sub('-+', "-", stem)
                stem = urllib.parse.quote(stem)
            self.webp_ref_path = self.ref_path.with_stem(stem).with_suffix(
                ".webp")
            if self.is_webp:
                self.webp_copy_exists = None
            else:
                self.webp_copy_exists = self.webp_ref_path.is_file()
        if self.img_encoding:
            self.img_encoding = self.img_encoding.lower()
            if self.img_encoding == 'jpeg':
                if Path(self.img_path_on_disk).suffix[1:].lower() in {
                        "jpeg", "jpg"
                }:
                    self.correct_extension = True
                else:
                    self.correct_extension = False
            else:
                self.correct_extension = Path(
                    self.img_path_on_disk).suffix[1:].lower(
                    ) == self.img_encoding.lower()
        else:
            self.correct_extension = None
        self.img_ref_external_web_link = str(self.ref_path).startswith("http")

    def print_ref(self):
        '''
        Prints the `img_ref`'s main data to the screen.
        The data that is printed out are:
            -The file path for the referenced image
            -The image's encoding protocol (png, jpeg, webp)
            -The reference file that contains this specific reference and the
                line of the reference file that contains this specific reference
                Note: The line is only necessary for DB files. For JSON files,
                a "-1" will be printed instead.
            -The full JSON address of the reference
            -The first 255 characters of the content of the reference.
        Note: the multiple parts are separated by a "pipe" ( the | character).


        INPUTS:
        -------
        None

        RETURNS:
        --------
        None

        EXAMPLE:
        --------
        # Input:
        my_ref.printref()

        # Output:
        # worlds/porvenir/art/porvenir-banner.webp | webp | worlds/porvenir/world.json -1 | ['description'] | <img title="The Secret of the Porvenir" src="worlds/porvenir/art/porvenir-banner.webp" />The Secret of the Porvenir is a spooktacular game-ready adventure for 5th Edition.<blockquote>The Porvenir - missing for weeks, feared lost - has mysteriously returne |
        '''

        print_str = f'{self.ref_path} | '
        print_str = print_str + f'{self.img_encoding if self.img_encoding else "404 IMG NOT FOUND"} | '
        print_str = print_str + f'{self.json_address} | '
        print_str = print_str + f'{self.get_img_ref_content()[:255]} | '
        print(print_str)

    def create_webp_copy(self):
        '''
        Creates a compressed ".webp" copy of the image being referenced in the
        `img_ref` object.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        subprocess_output.returncode (INT) : Indicates whether or not the conversion
            process terminated successfully. This value takes 0 if the conversion
            was successful. All other values indicate some sort of problem.

        EXAMPLE:
        --------
        # Input:
        my_ref.create_webp_copy()

        # Output:
        # None
        '''
        # The actual string that needs to be sent to the command line
        cmd_call_str = f'"{self.world_ref.ffmpeg_location}" -y -i "{self.img_path_on_disk}" -c:v libwebp "{self.webp_ref_path}" -hide_banner -loglevel error'

        # Running terminal command (https://stackoverflow.com/a/48857230/8667016)
        # The exit code here is 0 if the conversion succeeded. If it is anything
        # else, it means the conversion process failed.
        subprocess_output = subprocess.run(shlex.split(cmd_call_str))
        return subprocess_output.returncode

    def push_updated_content_to_world(self, updated_content):
        ''''
        Pushes content from the `updated_content` string back into the
        `WorldRefs` object.

        INPUTS:
        -------
        updated_content (STR) : Content that will be pushed back into the
            `WorldRefs` object.

        RETURNS:
        --------
        subprocess_output.returncode (INT) : Indicates whether or not the conversion
            process terminated successfully. This value takes 0 if the conversion
            was successful. All other values indicate some sort of problem.

        EXAMPLE:
        --------
        # Input:
        my_ref.push_updated_content_to_world(updated_content)

        # Output:
        # None
        '''
        d = self.world_ref.files[self.ref_file_type][self.ref_file_path]
        if self.ref_file_type == 'db':
            d = d[self.ref_file_line]
        edit_nested_dict_recursive(d, self.json_address, updated_content)


class WorldRefs:
    '''
    Container object that represents the Foundry World. This object contains
    several helper attributes and methods, such as a function that searches the
    world folder for all the image files, and an attribute that is a list of
    all the `img_ref`s inside the world.

    Main attributes:
        self.user_data_folder (STR) : String that describes the absolute path for
            the user data folder on disk. On Windows installations, this attribute
            should typically look something like this: "C:/Users/jegasus/AppData/Local/FoundryVTT/Data"
        self.world_folder (STR) : String that describes the relative path to the
            world folder to be scanned by the world reference tool. This path needs
            to be relative to the user data folder (i.e., the combination of the
            `user_data_folder` attribute and the `world_folder` represent the
            absolute path of the World folder to be scanned. This attribute should
            typically look like this: "worlds/porvenir", or "worlds/kobold-cauldron".
        self.core_data_folder (STR) : String that describes the absolute path to the
            Foundry Core Data folder. This attribute should typically look like
            this: "C:/Program Files/FoundryVTT/resources/app/public"
        self.ffmpeg_location (STR) : String that describes the absolute path to
            the ffmpeg executable. This attribute should typically look like this:
            "C:/Program Files (x86)/Audacity/libraries/ffmpeg.exe".
        self.trash_folder (STR): String that describes the relative path to the
            trash folder for this world. This path is relative to the path in the
            `user_data_folder` attribute. This attribute should typically look
            like this: "worlds/porvenir/_trash", or "worlds/kobold-cauldron_trash".
        self.trash_queue (SET) : Set of filenames that need to be moved to the
            trash folder.
        self.all_img_refs (LIST) : List of all the `img_ref` objects found in
            the world's JSON and DB files.
        self.all_img_refs_by_id (DICT) : Dictionary of all `img_ref` objects
            indexed by `ref_id`
        self.json_files (DICT) : Dictionary that holds the contents of all the
            JSON files inside the World folder. The structure of this dictionary
            is as follows:
                {'worlds/porvenir/world.json' : {json_dict_content},
                 'worlds/porvenir/descr.json' : {json_dict_content}}
        self.db_files (DICT) : Dictionary that holds the contents of all the
            DB files inside the World folder. The structure of this dictionary
            is as follows:
                {'worlds/porvenir/data/actors.db   : [{json_dict_content},
                                                      {json_dict_content},
                                                      {json_dict_content}],
                 'worlds/porvenir/data/folders.db' : [{json_dict_content},
                                                      {json_dict_content},
                                                      {json_dict_content}]
                 'worlds/porvenir/data/items.db'   : [{json_dict_content},
                                                      {json_dict_content},
                                                      {json_dict_content}] }

    '''
    def __init__(self, user_data_folder, world_folder, core_data_folder,
                 ffmpeg_location):
        '''
        Function used to instantiate new objects from the `WorldRefs` class.

        INPUTS:
        -------
        user_data_folder (STR) : String that describes the absolute path for
            the user data folder on disk. On Windows installations, this attribute
            should typically look something like this: "C:/Users/jegasus/AppData/Local/FoundryVTT/Data"
        world_folder (STR) : String that describes the relative path to the
            world folder to be scanned by the world reference tool. This path needs
            to be relative to the user data folder (i.e., the combination of the
            `user_data_folder` attribute and the `world_folder` represent the
            absolute path of the World folder to be scanned. This attribute should
            typically look like this: "worlds/porvenir", or "worlds/kobold-cauldron".
        core_data_folder (STR) : String that describes the absolute path to the
            Foundry Core Data folder. This attribute should typically look like
            this: "C:/Program Files/FoundryVTT/resources/app/public"
        ffmpeg_location (STR) : String that describes the absolute path to
            the ffmpeg executable. This attribute should typically look like this:
            "C:/Program Files (x86)/Audacity/libraries/ffmpeg.exe".


        RETURNS:
        --------
        WorldRefs (OBJECT) : The newly created `WorldRefs` object itself.

        EXAMPLE:
        --------
        # Input:
        my_WorldRefs = WorldRefs(
                user_data_folder='C:/Users/jegasus/AppData/Local/FoundryVTT/Data',
                world_folder='worlds/porvenir',
                core_data_folder='C:/Program Files/FoundryVTT/resources/app/public',
                ffmpeg_location='C:/Program Files (x86)/Audacity/libraries/ffmpeg.exe')

        # Output:
        # None
        '''
        self.user_data_folder = user_data_folder
        self.world_folder = world_folder
        self.core_data_folder = core_data_folder
        self.ffmpeg_location = ffmpeg_location

        # Reading in the DB and JSON files inside the world
        self.load_data()

        # Making the trash folder. This is where all the images to be deleted
        # will go before they are actually deleted.
        trash = Path(self.world_folder / '_trash')
        trash.mkdir(exist_ok=True)
        self.trash = trash

        # Set of images that need to be moved to the trash
        self.trash_queue = set()

        # Finds all the `img_ref` objects inthe world
        self.find_all_img_references_in_world()

    def load_data(self):
        self.files = {"json": {}, "db": {}}
        for path in [p for p in Path(self.world_folder).rglob('*.db')]:
            if path != Path(self.world_folder / 'data/settings.db'):
                with open(path, encoding="utf-8") as file:
                    lines = [json.loads(line) for line in file]
                self.files["db"][path] = lines
        self.json_files = {}
        for path in [p for p in Path(self.world_folder).rglob('*.json')]:
            with open(path, 'r', encoding="utf-8") as fp:
                self.files["json"][path] = [json.load(fp)]

    def find_all_img_references_in_world(self, return_result=False):
        '''
        Scans the DB and JSON files inside the world and creates `img_ref`
        objects for each and every reference to image files. All of the `img_ref`
        objects that are created in this process are appended to a list. This
        list of `img_ref`s is added as an attribute of the `WorldRefs` object.

        Attributes set by this function:
            self.all_img_refs (LIST) : List of all the `img_ref` objects found in
                the world's JSON and DB files.

        INPUTS:
        -------
        return_result (BOOL) : Indicates whether or not the function should return
            the `all_img_refs` list at the end of the process.

        RETURNS:
        --------
        all_img_refs (LIST) :  List of all the `img_ref` objects found in
            the world's JSON and DB files.

        '''
        self.all_img_refs = []
        self.all_img_refs_by_id = {}
        for file_type, files in self.files.items():
            for path, file in files.items():
                for i, content in enumerate(file):
                    self.traverse_dict_and_find_all_refs(
                        content, path, file_type, i)
        if return_result:
            return self.all_img_refs

    def traverse_dict_and_find_all_refs(self,
                                        dict_content=None,
                                        ref_file_path=None,
                                        json_or_db=None,
                                        ref_file_line=None):
        '''
        Function that traverses a JSON-like dictionary looking for references
        to images. For each reference that is found, an `img_ref` object is created
        and appended to the `self.all_img_refs` list.

        INPUTS:
        -------
        dict_content (DICT) : JSON-like content of the DB or JSON file.
        ref_file_path (STR) : Relative file path to the reference file that is
            being traversed. For example: 'worlds/porvenir/world.json' or
            'worlds/porvenir/data/actors.db'.
        json_or_db (STR) : String that describes whether the reference file being
            traversed is a DB file or a JSON file. The acceptable/valid values
            for this variable are exclusively "json" or "db".
        ref_file_line (INT or None): For '.db' reference files, there are multiple
            JSON-like dictionaries per row. The `ref_file_line` argument indicates
            which line in the ".db" file this particular `img_ref` can be found.
            For example, if the reference to the image is on the 5th line of the
            "journal.db" file, then `ref_file_line` will equal 4. In cases where
            the reference was found in a ".json" file, this attribute is instead
            set to None.
            NOTE: As with everything else in Python, this line number is zero-indexed.

        RETURNS:
        --------
        None

        '''
        regex_img_exp = re.compile(r'\.webp|\.jpg|\.jpeg|\.png')

        # Within each leaf of the dict tree, see if there is a
        # reference to an image.
        for item in dict_walker(dict_content):

            item_content = item[-1]
            if type(item_content) == str:

                # If an image extension is found, extract the full file path
                if regex_img_exp.findall(item_content):
                    img_ref_content = item_content
                    # Check if leaf is an HTML block
                    if BeautifulSoup(img_ref_content, 'html.parser').find():
                        # If it is an HTML block, search for images
                        img_html_matches = BeautifulSoup(
                            img_ref_content, 'html.parser').findAll("img")
                        unique_img_refs_in_html = {}
                        for match in img_html_matches:
                            if match['src'] not in unique_img_refs_in_html:
                                unique_img_refs_in_html[match['src']] = 1
                            else:
                                unique_img_refs_in_html[match['src']] += 1

                        # For every image found, generate a reference_dict
                        for img_ref in unique_img_refs_in_html:
                            ref_obj = ImageReference(
                                ref_file_type=json_or_db,
                                ref_file_path=ref_file_path,
                                ref_file_line=ref_file_line
                                if json_or_db == 'db' else None,
                                full_json_address=item,
                                ref_path=img_ref,
                                WorldRefs_obj=self)
                            self.all_img_refs.append(ref_obj)
                            self.all_img_refs_by_id[ref_obj.ref_id] = ref_obj

                    # If the leaf is not an HTML chunk, it's an img reference,
                    # so we just need to add it to the list of references.
                    else:
                        ref_obj = ImageReference(ref_file_type=json_or_db,
                                                 ref_file_path=ref_file_path,
                                                 ref_file_line=ref_file_line
                                                 if json_or_db == 'db' else 0,
                                                 full_json_address=item,
                                                 ref_path=img_ref_content,
                                                 WorldRefs_obj=self)
                        self.all_img_refs.append(ref_obj)
                        self.all_img_refs_by_id[ref_obj.ref_id] = ref_obj

    def fix_incorrect_file_extensions(self):
        '''
        Looks into the world's `img_ref`s and checks if their encoding matches
        the one in their respective file extensions.
        For example, consider that an `img_ref` points to a file on disk called
        "worlds/myworld/myimg.jpeg", but the actual encoding used for the image
        is "PNG". In that case, this function renames the file on disk to be
        "worlds/myworld/myimg.png", updates all the `img_ref` objects that point
        to that image and updates the `WorldRefs` object.
        NOTE: This mehtod does not belong to the `img_ref` class on purpose!
        That's because one single image on disk can have multiple references in
        the world.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        None

        '''
        refs_indexed_by_img = self.get_refs_indexed_by_img()

        # Looping over every image found in references
        for img_path in refs_indexed_by_img:
            temp_ref = refs_indexed_by_img[img_path][0]

            # Ensuring that we only try to "fix" extensions for images that are
            # inside the world folder and that actually exist on disk
            if temp_ref.img_exists and temp_ref.ref_img_in_world_folder and not temp_ref.correct_extension:
                old_content = temp_ref.get_img_ref_content()
                old_ref_path = temp_ref.ref_path

                suffix = f".{temp_ref.img_encoding}"

                new_ref_path = find_filename_that_doesnt_exist_yet(
                    Path(old_ref_path), suffix)

                new_content = old_content.replace(str(old_ref_path),
                                                  str(new_ref_path))

                shutil.copyfile(old_ref_path, new_ref_path)

                # After the file on disk was fixed, all the `img_ref`s that
                # pointed to the old image need to be updated
                for ref in refs_indexed_by_img[img_path]:
                    ref.set_editable_attributes(new_ref_path)
                    ref.push_updated_content_to_world(new_content)

    def find_all_images_in_world_folder(self):
        '''
        Returns a list containing all of the images inside the World folder.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        all_images_in_world_folder (LIST) : List containing all of the images
            inside the World folder.

        '''
        # Using rglob to find multiple patterns:
        types = ('*.jpg', '*.jpeg', '*.png', '*.webp')
        all_images_in_world_folder = []
        for file_type in types:
            all_images_in_world_folder.extend(
                list(Path(self.world_folder).rglob(file_type)))

        return all_images_in_world_folder

    def get_all_unused_images_in_world_folder(self):
        '''
        INPUTS:
        -------
        Searches the world folder for all image files and compares it to the
        images being referenced in all of the `img_ref` objects.
        In the end, the function returns the list of unused images.

        RETURNS:
        --------
        unused_images_in_world_folder (LIST) : list of all the unused images
            inside the world folder.

        '''
        # Getting a list of all images on disk inside the World folder.
        all_images_in_world_folder = self.find_all_images_in_world_folder()

        # Making a counter for each image inside the World folder.
        all_images = {}
        for img in all_images_in_world_folder:
            all_images[img] = 0

        # Looping over every `img_ref`. For each image found, we increment the
        # respective counter.
        for ref in self.all_img_refs:
            if ref.img_path_on_disk in all_images:
                all_images[ref.img_path_on_disk] += 1

        # Fishing out only images whose counters remain at zero.
        unused_images = []
        for image in all_images:
            if all_images[image] == 0:
                unused_images.append(image)
        return unused_images

    def add_unused_images_to_trash_queue(self):
        '''
        INPUTS:
        -------
        Scans the World folder for unused images and adds them all to the trash
        queue.

        RETURNS:
        --------
        None

        '''
        # Getting the list of unised images in World folder
        unused = self.get_all_unused_images_in_world_folder()

        # Adding all of them to the `trash_queue`
        for img in unused:
            self.trash_queue.add(img)

    def get_broken_refs(self):
        '''
        INPUTS:
        -------
        Scans the World and finds references to images that do not exist on disk.
        In the end, the list of broken references is returned.

        RETURNS:
        --------
        broken_refs (LIST) : List of `img_ref` objects containing references to
            images that do not exist on disk.

        '''
        broken_ref_count = 0
        broken_refs = []

        # Looping over every `img_ref` object searching for references to files
        # that don't exist in disk or that have already been added to the trash queue.
        for ref in self.all_img_refs:
            if ((ref.img_path_on_disk is None) and
                (not ref.img_ref_external_web_link)) or (ref.img_path_on_disk
                                                         in self.trash_queue):
                broken_ref_count += 1
                broken_refs.append(ref)
        return broken_refs

    def try_to_fix_one_broken_ref(self, img_ref_to_fix):
        '''
        Some older Foundry worlds pointed to the "modules" folder instead of the
        "worlds" folder. This function takes one single `img_ref` object that points
        to a file on disk that does not exist and checks if it points to an image
        inside the "modules" folder instead. If it does, it tries to search for
        a file on disk with the same file path, but substituting "modules" with
        "worlds". If this new file path points to an image that actually exists,
        the `img_ref` is updated accordingly.

        INPUTS:
        -------
        img_ref_to_fix (OBJECT) : An `img_ref` object whose file on disk will be
            investigated for potential substitution from the "modules" folder
            to the "worlds" folder.

        RETURNS:
        --------
        broken_ref_fixed (BOOL) : Indicates whether or not the `img_ref` object
            being evaluated was fixed.

        '''
        # The default value below assumes that the broken ref will remain broken
        broken_ref_fixed = False

        # Checks if the `img_ref` points to the "modules" folder
        if str(img_ref_to_fix.ref_path)[:7] == 'modules':

            # If it does, we try to swap the "modules" folder for the "world"
            # folder and see if this new file exists on disk. If so, the reference
            # is fixed!
            new_ref_path = Path(
                str(img_ref_to_fix.ref_path).replace('modules', 'worlds'))
            if new_ref_path.is_file():
                new_img_content = img_ref_to_fix.get_img_ref_content().replace(
                    str(img_ref_to_fix.ref_path), str(new_ref_path))
                img_ref_to_fix.set_editable_attributes(new_ref_path)
                img_ref_to_fix.push_updated_content_to_world(new_img_content)
                broken_ref_fixed = True
        return broken_ref_fixed

    def try_to_fix_all_broken_refs(self):
        '''
        Some older Foundry worlds pointed to the "modules" folder instead of the
        "worlds" folder. This function scans all of the `img_ref`s in the World
        and tried to fix them all. See the `try_to_fix_one_broken_ref` mehtod
        for more info.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        None

        '''
        broken_refs = self.get_broken_refs()
        #broken_ref_imgs = self.get_refs_indexed_by_img(broken_refs)
        #print(f'Number of broken references: {len(broken_refs)}\n'
        #      f'Number of images with broken references: {len(list(broken_ref_imgs.keys()))}\n')
        broken_ref_fixed_counter = 0
        for ref in broken_refs:
            broken_ref_fixed_counter += self.try_to_fix_one_broken_ref(ref)
        print(f'Fixed {broken_ref_fixed_counter} broken refs by pointing to'
              ' `worlds` folder instead of `modules` folder.')
        #broken_refs = self.get_broken_refs()
        #print(f'Number of broken references after fix: {len(broken_refs)}')

    def print_broken_ref_details(self):
        '''
        Prints main details regarding broken refs: how many broken refs there
        are and how many actual images have broken refs.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        None
        '''
        broken_refs = self.get_broken_refs()
        broken_ref_imgs = self.get_refs_indexed_by_img(broken_refs)
        print(
            f'Number of broken references: {len(broken_refs)}\n'
            f'Number of images with broken references: {len(list(broken_ref_imgs.keys()))}\n'
        )

    def get_refs_indexed_by_hash_by_img(self, input_ref_list=None):
        '''
        Searches all the `img_ref`s in the world and builds an index of all the
        references. The dictionary created by this function indexes the refeences
        by hash and by image file path.

        INPUTS:
        -------
        input_ref_list (LIST or None) : List of references to be indexes. When
            this input is left blank (equal to "None"), the default behavior is
            to just index all of the `img_ref`s in the `self.all_img_refs`
            attribute.

        RETURNS:
        --------
        refs_indexed_by_hash_by_img (DICT) : Dictionary that indexes all of the
            `img_ref` objects by their hashes and by the file paths of the images.
            Structure of output:
            refs_indexed_by_hash_by_img = {'hash_a':{'img_1':[ref_i,
                                                              ref_ii,
                                                              ref_iii],
                                                     'img_2':[ref_iv,
                                                              ref_v,
                                                              ref_vi,
                                                              ref_vii]}}
        '''
        # Preparing dictionary for indexing
        refs_indexed_by_hash_by_img = {}

        # Checking which ref_list to use
        if input_ref_list == None:
            ref_list = self.all_img_refs
        else:
            ref_list = input_ref_list

        # Looping over all of the `img_ref`s in `ref_list`
        for ref in ref_list:
            if ref.img_hash not in refs_indexed_by_hash_by_img:
                refs_indexed_by_hash_by_img[ref.img_hash] = {}

            if ref.ref_path not in refs_indexed_by_hash_by_img[ref.img_hash]:
                refs_indexed_by_hash_by_img[ref.img_hash][ref.ref_path] = []

            refs_indexed_by_hash_by_img[ref.img_hash][ref.ref_path].append(ref)

        return refs_indexed_by_hash_by_img

    def get_duplicated_images(self):
        '''
        Scans all of the `img_ref` objects and finds which ones are duplicates
        of each other. The results of this function are indexed by hash.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        duplicated_images (DICT) : Dictionary that indexes the `img_ref` objects
            by hash and by image file.
            Structure of output:
            duplicated_images = {'hash_a':{'img_1':[ref_i,
                                                    ref_ii,
                                                    ref_iii],
                                           'img_2':[ref_iv,
                                                    ref_v,
                                                    ref_vi,
                                                    ref_vii]}}
        '''
        refs_indexed_by_hash_by_img = self.get_refs_indexed_by_hash_by_img()

        duplicated_images_count_by_hash = 0
        duplicated_images = {}
        for obj_hash in refs_indexed_by_hash_by_img:
            if (len(refs_indexed_by_hash_by_img[obj_hash]) > 1) and (obj_hash
                                                                     != None):
                duplicated_images[obj_hash] = refs_indexed_by_hash_by_img[
                    obj_hash]
                duplicated_images_count_by_hash += 1

        return duplicated_images

    def fix_one_set_of_duplicated_images(self, duplicated_img_dict=None):
        '''
        Given a set of duplicated images, this function "fixes" all of the
        references. Fixing them involves making all of the `img_ref` objects point
        to one single image, the new `img_ref` info is pushed to the world and
        the unreferenced images are added to the trash queue.

        INPUTS:
        -------
        this_duplicated_img_dict (DICT) : a dictionary of `img_ref`s that point
        to different files on disk but which are all duplicated images. The
        dictionary is indexed by file path.
            Structure of input:
            duplicated_images = {'img_1':[ref_i,
                                          ref_ii,
                                          ref_iii],
                                 'img_2':[ref_iv,
                                          ref_v,
                                          ref_vi,
                                          ref_vii]}

        RETURNS:
        --------
        None

        '''
        main_img = list(duplicated_img_dict.keys())[0]
        imgs_to_be_replaced = list(duplicated_img_dict.keys())[1:]

        for img_to_be_replaced in imgs_to_be_replaced:
            refs = duplicated_img_dict[img_to_be_replaced]
            for ref in refs:
                updated_content = ref.get_img_ref_content().replace(
                    str(ref.img_path_on_disk), str(main_img))
                ref.set_editable_attributes(main_img)
                ref.push_updated_content_to_world(updated_content)

            self.trash_queue.add(img_to_be_replaced)

    def fix_all_sets_of_duplicated_images(self):
        '''
        Scans all `img_ref`s in a world and fixes all of the sets of duplicated
        images.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        None

        '''
        duplicated_images = self.get_duplicated_images()

        for obj_hash in duplicated_images:
            img_dict = duplicated_images[obj_hash]
            self.fix_one_set_of_duplicated_images(img_dict)

        duplicated_images = self.get_duplicated_images()

    def update_one_ref_to_webp(self, img_ref_to_update=None):
        '''
        Updates one single `img_ref` object such that it points to the ".webp"
        image on disk instead of whatever the original file type was.

        INPUTS:
        -------
        img_ref_to_update (OBJECT) : instance of the `img_ref` class that will
            be updated by this function.

        RETURNS:
        --------
        None
        '''
        old_ref_path = img_ref_to_update.ref_path
        old_img_ref_content = img_ref_to_update.get_img_ref_content()

        new_ref_path = img_ref_to_update.webp_ref_path
        new_img_ref_content = old_img_ref_content.replace(
            str(old_ref_path), str(new_ref_path))

        img_ref_to_update.set_editable_attributes(new_ref_path)
        img_ref_to_update.push_updated_content_to_world(new_img_ref_content)

    def get_refs_indexed_by_img(self, input_ref_list=None):
        '''
        Creates a dictionary that indexes all of the `img_ref` objects inside a
        Foundry World by file path.

        INPUTS:
        -------
        input_ref_list (LIST or None) : List of references to be indexes. When
            this input is left blank (equal to "None"), the default behavior is
            to just index all of the `img_ref`s in the `self.all_img_refs`
            attribute.

        RETURNS:
        --------
        refs_indexed_by_img (DICT) : dictionary that indexes `img_ref` objects
            by the image file paths.
            Structure of output:
            refs_indexed_by_img = {'img_1':[ref_i,
                                            ref_ii,
                                            ref_iii],
                                   'img_2':[ref_iv,
                                            ref_v,
                                            ref_vi,
                                            ref_vii]}
        '''
        # Preparing dictionary for output
        refs_indexed_by_img = {}

        # Checking which ref_list to use
        if input_ref_list == None:
            refs = self.all_img_refs
        else:
            refs = input_ref_list

        # Looping all the `img_ref`s in `ref_list`
        for ref in refs:
            if ref.ref_path not in refs_indexed_by_img:
                refs_indexed_by_img[ref.ref_path] = []
            refs_indexed_by_img[ref.ref_path].append(ref)
        return refs_indexed_by_img

    def convert_all_images_to_webp_and_update_refs(self):
        '''
        Converts all of the images referenced in a Foundry World into a ".webp"
        format, updates all of the `img_ref` objects and pushes all of the
        updated data back into the `WorldRefs` object.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        None

        '''
        refs_indexed_by_img = self.get_refs_indexed_by_img()

        printed_percentages = {}

        for img_counter, path in enumerate(refs_indexed_by_img):
            temp_ref = refs_indexed_by_img[path][0]
            temp_path_for_deletion = path
            percent_imgs_checked = int(100 * img_counter /
                                       len(refs_indexed_by_img))
            if (percent_imgs_checked % 10 == 0) & (percent_imgs_checked
                                                   not in printed_percentages):
                printed_percentages[percent_imgs_checked] = True
                print(f'Scanned {percent_imgs_checked}% of all images.')
            if (not temp_ref.is_webp) and (temp_ref.img_exists) and (
                    temp_ref.ref_img_in_world_folder):
                return_code = 0
                if not temp_ref.webp_ref_path.is_file():
                    return_code = temp_ref.create_webp_copy()
                if not return_code and temp_ref.webp_ref_path.is_file():
                    for ref in refs_indexed_by_img[path]:
                        self.update_one_ref_to_webp(ref)
                self.trash_queue.add(temp_path_for_deletion)
        print('Scanned 100% of all images.')

    def export_all_json_and_db_files(self):
        '''
        Creates a backup of the ".json" & ".db" files on disk and exports the
        data inside the `WorldRefs` object into new ".json" & ".db" files onto
        the disk.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        None

        '''
        for files in self.files.values():
            for path, content in files.items():
                shutil.copyfile(path, path.with_suffix(path.suffix + "bak"))
                with open(path, 'w', encoding="utf-8") as file:
                    lines = (json.dumps(l,
                                        separators=(',', ':'),
                                        ensure_ascii=False) for l in content)
                    file.write("\n".join(lines))

    def find_refs_by_img_path(self, img_path_to_search=None):
        '''
        Gets a list of all the `img_ref` objects that point to a specific file
        on disk.

        INPUTS:
        -------
        img_path_to_search (STR) : string that describes the file path of the
            image being searched.

        RETURNS:
        --------
        found_refs (LIST) : list of `img_ref` objects that all point to the same
            image file on disk.

        '''
        found_refs = []
        for ref in self.all_img_refs:
            if ref.ref_path == img_path_to_search:
                found_refs.append(ref)
        return found_refs

    def move_all_imgs_in_trash_queue_to_trash(self):
        '''
        Function used to actually move the files from the `trash_queue` into the
        "_trash" folder inside the world.

        INPUTS:
        -------
        None


        RETURNS:
        --------
        None

        '''
        for file in self.trash_queue:

            # Making sure that the file exists and that it is actually inside
            # the world folder. This is to prevent accidentally moving images
            # from the Foundry Core folder
            exists = file.is_file()
            if not exists:
                unquoted = file.with_stem(urllib.parse.unquote(file.stem))
                if unquoted.is_file():
                    exists = True
                    file = unquoted
            if (exists and re.match('.*' + str(self.world_folder) + '.*',
                                    str(file))):
                file.rename(self.trash / file.name)

    def empty_trash(self, delete_unreferenced_images=False):
        '''
        Actually deletes the content inside the "_trash" folder inside the world.
        Careful when using this function!!! This function has no "undo"!!!!!

        INPUTS:
        -------
        delete_unreferenced_images_bool (BOOL) : indicates whether or not the
            files in the "_trash" folder should actually be deleted. When this
            input is set to "False", the function will simply terminate without
            deleting anything.

        RETURNS:
        --------
        None

        '''
        if delete_unreferenced_images:
            shutil.rmtree(self.trash)

    def restore_bak_files(self):
        '''
        Restores the ".jsonbak" and "dbbak" files to ".json" and ".db" respectively.
        Note: this process overwrites whatever was in their places.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        None
        '''
        db_paths = [p for p in Path(self.world_folder).rglob('*.dbbak')]
        json_paths = [p for p in Path(self.world_folder).rglob('*.jsonbak')]

        for path in db_paths + json_paths:
            shutil.move(
                path,
                path.with_suffix(path.suffix[:-3]),
            )

    def restore_trash_folder(self):
        '''
        Restores files that got sent to the "_trash" folder.

        INPUTS:
        -------
        None

        RETURNS:
        --------
        None
        '''
        for path in Path(self.trash_folder).iterdir():
            shutil.move(self.trash_folder / path, self.world_folder / path)


def input_checker(user_data_folder=None,
                  world_folder=None,
                  core_data_folder=None,
                  ffmpeg_location="ffmpeg",
                  delete_unreferenced_images=False):
    '''
    Checks all of the inputs to make sure they are valid. For the folder inputs,
    it checks that the folders exist. For the FFMPEG input, it checks if the
    ".exe" executable file exists on disk. For the flag that determines whether
    or not files will actually be deleted, it checks if the input is "y" or "n".

    !!!Note: This is also where the working directory is set!


    INPUTS:
    -------
    user_data_folder (STR) : String that describes the absolute path for
        the user data folder on disk. On Windows installations, this attribute
        should typically look something like this: "C:/Users/jegasus/AppData/Local/FoundryVTT/Data"
    world_folder (STR) : String that describes the relative path to the
        world folder to be scanned by the world reference tool. This path needs
        to be relative to the user data folder (i.e., the combination of the
        `user_data_folder` attribute and the `world_folder` represent the
        absolute path of the World folder to be scanned. This attribute should
        typically look like this: "worlds/porvenir", or "worlds/kobold-cauldron".
    core_data_folder (STR) : String that describes the absolute path to the
        Foundry Core Data folder. This attribute should typically look like
        this: "C:/Program Files/FoundryVTT/resources/app/public"
    ffmpeg_location (STR) : String that describes the absolute path to
        the ffmpeg executable. This attribute should typically look like this:
        "C:/Program Files (x86)/Audacity/libraries/ffmpeg.exe".
    delete_unreferenced_images (STR) : string that indicates whether or not the
        files that got placed in the "_trash" folder should actually be deleted
        at the end of the process. This attribute expects either "y" or "n".


    RETURNS:
    --------
    checked_inputs (DICT) : A dictionary containing the verified and modified
        inputs.

    EXAMPLE:
    --------
    # Input:
    checked_inputs = input_checker(user_data_folder = "C:/Users/jegasus/AppData/Local/FoundryVTT/Data",
                                   world_folder     = "worlds/porvenir",
                                   core_data_folder = "C:/Program Files/FoundryVTT/resources/app/public",
                                   ffmpeg_location  = "C:/Program Files (x86)\Audacity/libraries/ffmpeg.exe",
                                   delete_unreferenced_images="n")

    user_data_folder_checked = checked_inputs["user_data_folder"]
    world_folder_checked = checked_inputs["world_folder"]
    core_data_folder_checked = checked_inputs["core_data_folder"]
    ffmpeg_location_checked = checked_inputs["ffmpeg_location"]
    delete_unreferenced_images_checked = checked_inputs["delete_unreferenced_images_checked"]
    '''
    if not (user_data_folder := Path(user_data_folder)).is_dir():
        raise NotADirectoryError(
            f'The `user_data_folder` supplied does not exist: {user_data_folder}'
        )

    if not Path(user_data_folder / world_folder).is_dir():
        raise NotADirectoryError(
            f'The `world_folder` supplied does not exist: {world_folder}')

    if not (core_data_folder := Path(core_data_folder)).is_dir():
        raise NotADirectoryError(
            f'The `core_data_folder` supplied does not exist: {core_data_folder}'
        )
    if not shutil.which(ffmpeg_location):
        raise NotADirectoryError(
            f'ffmpeg executable not found: {ffmpeg_location}')

    if delete_unreferenced_images.lower() == 'y':
        delete_unreferenced_images_bool = True
    elif delete_unreferenced_images.lower() == 'n':
        delete_unreferenced_images_bool = False
    else:
        raise ValueError(
            f'The value supplied to the `delete_unreferenced_images` flag \
                         is not valid. Please type in either "y" or "n".')

    checked_inputs = {
        'user_data_folder': user_data_folder,
        'world_folder': Path(world_folder),
        'core_data_folder': core_data_folder,
        'ffmpeg_location': ffmpeg_location,
        'delete_unreferenced_images': delete_unreferenced_images_bool
    }

    os.chdir(user_data_folder)

    return checked_inputs


def find_filename_that_doesnt_exist_yet(file_path, suffix):
    '''
    Function that recursively checks if a specific filename exists or not. The
    function keeps tacking on underscore characters ("_") until it finds a name
    of a file that doesn't yet exist on disk.

    INPUTS:
    -------
    file_path_before_extension (STR) : String of the image file path up until
    (and excluding) the file extension. For example, for the file located at
    "worlds/porvenir/art/wood-bg.jpg", the `file_path_before_extension` argument
    would be "worlds/porvenir/art/wood-bg".

    extension (STR) : String of just the file extension (without the period/dot).
    For example, for the file located at "worlds/porvenir/art/wood-bg.jpg", the
    `extension` would be "jpg".

    RETURNS:
    --------
    current_filename (STR) : String of the filename that doesn't yet exist on disk.
    For example, if we call this function for the file located at
    "worlds/porvenir/art/wood-bg.jpg" and that file does exist, but the file
    "worlds/porvenir/art/wood-bg_.jpg" does not, the function will return
    "worlds/porvenir/art/wood-bg_.jpg".

    EXAMPLE:
    --------
    # Suppose "worlds/porvenir/art/wood-bg.jpg" exists on disk, but
    # "worlds/porvenir/art/wood-bg_.jpg" does not.

    # Input:
    new_filename = find_filename_that_doesnt_exist_yet(
            "worlds/porvenir/art/wood-bg","jpg")
    print(new_filename)

    # Output:
    # "worlds/porvenir/art/wood-bg_.jpg"
    '''
    path = file_path.with_suffix(suffix)
    if path.is_file():
        return find_filename_that_doesnt_exist_yet(
            path.with_stem(path.stem + '_'), suffix)
    else:
        return path


# Function that does all that is needed for world compression in one single command
def one_liner_compress_world(user_data_folder=None,
                             world_folder=None,
                             core_data_folder=None,
                             ffmpeg_location=None,
                             delete_unreferenced_images=False):
    '''
    Main function to compress the Foudry World.

    INPUTS:
    -------
    user_data_folder (STR) : String that describes the absolute path for
        the user data folder on disk. On Windows installations, this attribute
        should typically look something like this: "C:/Users/jegasus/AppData/Local/FoundryVTT/Data"
    world_folder (STR) : String that describes the relative path to the
        world folder to be scanned by the world reference tool. This path needs
        to be relative to the user data folder (i.e., the combination of the
        `user_data_folder` attribute and the `world_folder` represent the
        absolute path of the World folder to be scanned. This attribute should
        typically look like this: "worlds/porvenir", or "worlds/kobold-cauldron".
    core_data_folder (STR) : String that describes the absolute path to the
        Foundry Core Data folder. This attribute should typically look like
        this: "C:/Program Files/FoundryVTT/resources/app/public"
    ffmpeg_location (STR) : String that describes the absolute path to
        the ffmpeg executable. This attribute should typically look like this:
        "C:/Program Files (x86)/Audacity/libraries/ffmpeg.exe".
    delete_unreferenced_images (STR) : string that indicates whether or not the
        files that got placed in the "_trash" folder should actually be deleted
        at the end of the process. This attribute expects either "y" or "n".

    RETURNS:
    --------
    None

    EXAMPLE:
    --------
    # Input:
    None

    # Output:
    # None
    '''
    checked_inputs = input_checker(user_data_folder, world_folder,
                                   core_data_folder, ffmpeg_location,
                                   delete_unreferenced_images)

    user_data_folder_checked = checked_inputs['user_data_folder']
    world_folder_checked = checked_inputs['world_folder']
    core_data_folder_checked = checked_inputs['core_data_folder']
    ffmpeg_location_checked = checked_inputs['ffmpeg_location']
    delete_unreferenced_images_checked = checked_inputs[
        'delete_unreferenced_images']

    refs = WorldRefs(user_data_folder_checked, world_folder_checked,
                     core_data_folder_checked, ffmpeg_location_checked)

    #my_WorldRefs.find_all_img_references_in_world()
    refs.try_to_fix_all_broken_refs()
    refs.fix_incorrect_file_extensions()
    refs.fix_all_sets_of_duplicated_images()
    refs.convert_all_images_to_webp_and_update_refs()
    refs.fix_all_sets_of_duplicated_images()
    refs.export_all_json_and_db_files()
    refs.add_unused_images_to_trash_queue()
    refs.move_all_imgs_in_trash_queue_to_trash()
    refs.empty_trash(delete_unreferenced_images_checked)

    return refs
