# -*- coding: utf-8 -*-

#   This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#     Copyright (C) 2018-2022 OzzieIsaacs
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program. If not, see <http://www.gnu.org/licenses/>.

import os

from . import logger, isoLanguages, cover
from .constants import BookMeta

try:
    from wand.image import Image
    use_IM = True
except (ImportError, RuntimeError) as e:
    use_IM = False

log = logger.create()

try:
    from comicapi.comicarchive import ComicArchive, MetaDataStyle
    use_comic_meta = True
    try:
        from comicapi import __version__ as comic_version
    except ImportError:
        comic_version = ''
except (ImportError, LookupError) as e:
    log.debug('Cannot import comicapi, extracting comic metadata will not work: %s', e)
    import zipfile
    import tarfile
    try:
        import rarfile
        use_rarfile = True
    except (ImportError, SyntaxError) as e:
        log.debug('Cannot import rarfile, extracting cover files from rar files will not work: %s', e)
        use_rarfile = False
    use_comic_meta = False


def _extract_cover_from_archive(original_file_extension, tmp_file_name, rar_executable):
    cover_data = extension = None
    if original_file_extension.upper() == '.CBZ':
        cf = zipfile.ZipFile(tmp_file_name)
        for name in cf.namelist():
            ext = os.path.splitext(name)
            if len(ext) > 1:
                extension = ext[1].lower()
                if extension in cover.COVER_EXTENSIONS:
                    cover_data = cf.read(name)
                    break
    elif original_file_extension.upper() == '.CBT':
        cf = tarfile.TarFile(tmp_file_name)
        for name in cf.getnames():
            ext = os.path.splitext(name)
            if len(ext) > 1:
                extension = ext[1].lower()
                if extension in cover.COVER_EXTENSIONS:
                    cover_data = cf.extractfile(name).read()
                    break
    elif original_file_extension.upper() == '.CBR' and use_rarfile:
        try:
            rarfile.UNRAR_TOOL = rar_executable
            cf = rarfile.RarFile(tmp_file_name)
            for name in cf.namelist():
                ext = os.path.splitext(name)
                if len(ext) > 1:
                    extension = ext[1].lower()
                    if extension in cover.COVER_EXTENSIONS:
                        cover_data = cf.read(name)
                        break
        except Exception as ex:
            log.debug('Rarfile failed with error: {}'.format(ex))
    return cover_data, extension


def _extract_cover(tmp_file_name, original_file_extension, rar_executable):
    cover_data = extension = None
    if use_comic_meta:
        archive = ComicArchive(tmp_file_name, rar_exe_path=rar_executable)
        for index, name in enumerate(archive.getPageNameList()):
            ext = os.path.splitext(name)
            if len(ext) > 1:
                extension = ext[1].lower()
                if extension in cover.COVER_EXTENSIONS:
                    cover_data = archive.getPage(index)
                    break
    else:
        cover_data, extension = _extract_cover_from_archive(original_file_extension, tmp_file_name, rar_executable)
    return cover.cover_processing(tmp_file_name, cover_data, extension)


def get_comic_info(tmp_file_path, original_file_name, original_file_extension, rar_executable):
    if use_comic_meta:
        archive = ComicArchive(tmp_file_path, rar_exe_path=rar_executable)
        if archive.seemsToBeAComicArchive():
            if archive.hasMetadata(MetaDataStyle.CIX):
                style = MetaDataStyle.CIX
            elif archive.hasMetadata(MetaDataStyle.CBI):
                style = MetaDataStyle.CBI
            else:
                style = None

            # if style is not None:
            loaded_metadata = archive.readMetadata(style)

            lang = loaded_metadata.language or ""
            loaded_metadata.language = isoLanguages.get_lang3(lang)

            return BookMeta(
                file_path=tmp_file_path,
                extension=original_file_extension,
                title=loaded_metadata.title or original_file_name,
                author=" & ".join([credit["person"]
                                   for credit in loaded_metadata.credits if credit["role"] == "Writer"]) or 'Unknown',
                cover=_extract_cover(tmp_file_path, original_file_extension, rar_executable),
                description=loaded_metadata.comments or "",
                tags="",
                series=loaded_metadata.series or "",
                series_id=loaded_metadata.issue or "",
                languages=loaded_metadata.language,
                publisher="",
                pubdate="",
                identifiers=[])

    return BookMeta(
        file_path=tmp_file_path,
        extension=original_file_extension,
        title=original_file_name,
        author='Unknown',
        cover=_extract_cover(tmp_file_path, original_file_extension, rar_executable),
        description="",
        tags="",
        series="",
        series_id="",
        languages="",
        publisher="",
        pubdate="",
        identifiers=[])
