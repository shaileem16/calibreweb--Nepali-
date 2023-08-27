# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2018-2019 OzzieIsaacs, cervinko, jkrehm, bodybybuddha, ok11,
#                            andy29485, idalin, Kyosfonica, wuqi, Kennyl, lemmsh,
#                            falgh1, grunjol, csitko, ytils, xybydy, trasba, vrabe,
#                            ruben-herold, marblepebble, JackED42, SiphonSquirrel,
#                            apetresc, nanu-c, mutschler
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program. If not, see <http://www.gnu.org/licenses/>.

import sys
from datetime import datetime

from flask import Blueprint, flash, redirect, request, url_for, abort
from flask_babel import gettext as _
from flask_login import current_user, login_required
from sqlalchemy.exc import InvalidRequestError, OperationalError
from sqlalchemy.sql.expression import func, true

from . import calibre_db, config, db, logger, ub
from .render_template import render_title_template
from .usermanagement import login_required_if_no_ano

log = logger.create()

shelf = Blueprint('shelf', __name__)


@shelf.route("/shelf/add/<int:shelf_id>/<int:book_id>", methods=["POST"])
@login_required
def add_to_shelf(shelf_id, book_id):
    xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).first()
    if shelf is None:
        log.error("Invalid shelf specified: %s", shelf_id)
        if not xhr:
            flash(_("अवैध शेल्फ निर्दिष्ट"), category="error")
            return redirect(url_for('web.index'))
        return "अवैध शेल्फ निर्दिष्ट", 400

    if not check_shelf_edit_permissions(shelf):
        if not xhr:
            flash(_("माफ गर्नुहोस्, तपाईंलाई त्यो शेल्फमा किताब थप्न अनुमति छैन"), category="error")
            return redirect(url_for('web.index'))
        return "Sorry you are not allowed to add a book to the that shelf", 403

    book_in_shelf = ub.session.query(ub.BookShelf).filter(ub.BookShelf.shelf == shelf_id,
                                                          ub.BookShelf.book_id == book_id).first()
    if book_in_shelf:
        log.error("Book %s is already part of %s", book_id, shelf)
        if not xhr:
            flash(_("पुस्तक पहिले नै शेल्फको अंश हो: %(shelfname)s", shelfname=shelf.name), category="error")
            return redirect(url_for('web.index'))
        return "पुस्तक पहिले नै शेल्फको अंश हो: %s" % shelf.name, 400

    maxOrder = ub.session.query(func.max(ub.BookShelf.order)).filter(ub.BookShelf.shelf == shelf_id).first()
    if maxOrder[0] is None:
        maxOrder = 0
    else:
        maxOrder = maxOrder[0]

    shelf.books.append(ub.BookShelf(shelf=shelf.id, book_id=book_id, order=maxOrder + 1))
    shelf.last_modified = datetime.utcnow()
    try:
        ub.session.merge(shelf)
        ub.session.commit()
    except (OperationalError, InvalidRequestError) as e:
        ub.session.rollback()
        log.error_or_exception("Settings Database error: {}".format(e))
        flash(_("उफ्! डाटाबेस त्रुटि: %(error)s.", error=e.orig), category="error")
        if "HTTP_REFERER" in request.environ:
            return redirect(request.environ["HTTP_REFERER"])
        else:
            return redirect(url_for('web.index'))
    if not xhr:
        log.debug("Book has been added to shelf: {}".format(shelf.name))
        flash(_("पुस्तक शेल्फमा थपिएको छ: %(sname)s", sname=shelf.name), category="success")
        if "HTTP_REFERER" in request.environ:
            return redirect(request.environ["HTTP_REFERER"])
        else:
            return redirect(url_for('web.index'))
    return "", 204


@shelf.route("/shelf/massadd/<int:shelf_id>", methods=["POST"])
@login_required
def search_to_shelf(shelf_id):
    shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).first()
    if shelf is None:
        log.error("Invalid shelf specified: {}".format(shelf_id))
        flash(_("अवैध शेल्फ निर्दिष्ट"), category="error")
        return redirect(url_for('web.index'))

    if not check_shelf_edit_permissions(shelf):
        log.warning("You are not allowed to add a book to the shelf".format(shelf.name))
        flash(_("तपाईंलाई शेल्फमा किताब थप्न अनुमति छैन"), category="error")
        return redirect(url_for('web.index'))

    if current_user.id in ub.searched_ids and ub.searched_ids[current_user.id]:
        books_for_shelf = list()
        books_in_shelf = ub.session.query(ub.BookShelf).filter(ub.BookShelf.shelf == shelf_id).all()
        if books_in_shelf:
            book_ids = list()
            for book_id in books_in_shelf:
                book_ids.append(book_id.book_id)
            for searchid in ub.searched_ids[current_user.id]:
                if searchid not in book_ids:
                    books_for_shelf.append(searchid)
        else:
            books_for_shelf = ub.searched_ids[current_user.id]

        if not books_for_shelf:
            log.error("Books are already part of {}".format(shelf.name))
            flash(_("पुस्तकहरू पहिल्यै सेल्फको अंश हुन्: %(name)s", name=shelf.name), category="error")
            return redirect(url_for('web.index'))

        maxOrder = ub.session.query(func.max(ub.BookShelf.order)).filter(ub.BookShelf.shelf == shelf_id).first()[0] or 0

        for book in books_for_shelf:
            maxOrder += 1
            shelf.books.append(ub.BookShelf(shelf=shelf.id, book_id=book, order=maxOrder))
        shelf.last_modified = datetime.utcnow()
        try:
            ub.session.merge(shelf)
            ub.session.commit()
            flash(_("पुस्तकहरू शेल्फमा थपिएका छन्: %(sname)s", sname=shelf.name), category="success")
        except (OperationalError, InvalidRequestError) as e:
            ub.session.rollback()
            log.error_or_exception("Settings Database error: {}".format(e))
            flash(_("उफ्! डाटाबेस त्रुटि: %(error)s.", error=e.orig), category="error")
    else:
        log.error("शेल्फमा पुस्तकहरू थप्न सकिएन: {}".format(shelf.name))
        flash(_("शेल्फमा पुस्तकहरू थप्न सकिएन: %(sname)s", sname=shelf.name), category="error")
    return redirect(url_for('web.index'))


@shelf.route("/shelf/remove/<int:shelf_id>/<int:book_id>", methods=["POST"])
@login_required
def remove_from_shelf(shelf_id, book_id):
    xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).first()
    if shelf is None:
        log.error("Invalid shelf specified: {}".format(shelf_id))
        if not xhr:
            return redirect(url_for('web.index'))
        return "अवैध शेल्फ निर्दिष्ट", 400

    # if shelf is public and use is allowed to edit shelfs, or if shelf is private and user is owner
    # allow editing shelfs
    # result   shelf public   user allowed    user owner
    #   false        1             0             x
    #   true         1             1             x
    #   true         0             x             1
    #   false        0             x             0

    if check_shelf_edit_permissions(shelf):
        book_shelf = ub.session.query(ub.BookShelf).filter(ub.BookShelf.shelf == shelf_id,
                                                           ub.BookShelf.book_id == book_id).first()

        if book_shelf is None:
            log.error("Book %s already removed from %s", book_id, shelf)
            if not xhr:
                return redirect(url_for('web.index'))
            return "Book already removed from shelf", 410

        try:
            ub.session.delete(book_shelf)
            shelf.last_modified = datetime.utcnow()
            ub.session.commit()
        except (OperationalError, InvalidRequestError) as e:
            ub.session.rollback()
            log.error_or_exception("Settings Database error: {}".format(e))
            flash(_("उफ्! डाटाबेस त्रुटि: %(error)s.", error=e.orig), category="error")
            if "HTTP_REFERER" in request.environ:
                return redirect(request.environ["HTTP_REFERER"])
            else:
                return redirect(url_for('web.index'))
        if not xhr:
            flash(_("पुस्तक शेल्फबाट हटाइयो: %(sname)s", sname=shelf.name), category="success")
            if "HTTP_REFERER" in request.environ:
                return redirect(request.environ["HTTP_REFERER"])
            else:
                return redirect(url_for('web.index'))
        return "", 204
    else:
        if not xhr:
            log.warning("You are not allowed to remove a book from shelf: {}".format(shelf.name))
            flash(_("माफ गर्नुहोस् तपाईलाई यो शेल्फबाट पुस्तक हटाउन अनुमति छैन"),
                  category="error")
            return redirect(url_for('web.index'))
        return "Sorry you are not allowed to remove a book from this shelf", 403


@shelf.route("/shelf/create", methods=["GET", "POST"])
@login_required
def create_shelf():
    shelf = ub.Shelf()
    return create_edit_shelf(shelf, page_title=_("एउटा शेल्फ सिर्जना गर्नुहोस्"), page="shelfcreate")


@shelf.route("/shelf/edit/<int:shelf_id>", methods=["GET", "POST"])
@login_required
def edit_shelf(shelf_id):
    shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).first()
    if not check_shelf_edit_permissions(shelf):
        flash(_("माफ गर्नुहोस् तपाईंलाई यो शेल्फ सम्पादन गर्न अनुमति छैन"), category="error")
        return redirect(url_for('web.index'))
    return create_edit_shelf(shelf, page_title=_("Edit a shelf"), page="shelfedit", shelf_id=shelf_id)


@shelf.route("/shelf/delete/<int:shelf_id>", methods=["POST"])
@login_required
def delete_shelf(shelf_id):
    cur_shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).first()
    try:
        if not delete_shelf_helper(cur_shelf):
            flash(_("शेल्फ मेटाउँदा त्रुटि भयो"), category="error")
        else:
            flash(_("शेल्फ सफलतापूर्वक मेटाइयो"), category="success")
    except InvalidRequestError as e:
        ub.session.rollback()
        log.error_or_exception("Settings Database error: {}".format(e))
        flash(_("उफ्! डाटाबेस त्रुटि: %(error)s.", error=e.orig), category="error")
    return redirect(url_for('web.index'))


@shelf.route("/simpleshelf/<int:shelf_id>")
@login_required_if_no_ano
def show_simpleshelf(shelf_id):
    return render_show_shelf(2, shelf_id, 1, None)


@shelf.route("/shelf/<int:shelf_id>", defaults={"sort_param": "order", 'page': 1})
@shelf.route("/shelf/<int:shelf_id>/<sort_param>", defaults={'page': 1})
@shelf.route("/shelf/<int:shelf_id>/<sort_param>/<int:page>")
@login_required_if_no_ano
def show_shelf(shelf_id, sort_param, page):
    return render_show_shelf(1, shelf_id, page, sort_param)


@shelf.route("/shelf/order/<int:shelf_id>", methods=["GET", "POST"])
@login_required
def order_shelf(shelf_id):
    shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).first()
    if shelf and check_shelf_view_permissions(shelf):
        if request.method == "POST":
            to_save = request.form.to_dict()
            books_in_shelf = ub.session.query(ub.BookShelf).filter(ub.BookShelf.shelf == shelf_id).order_by(
                ub.BookShelf.order.asc()).all()
            counter = 0
            for book in books_in_shelf:
                setattr(book, 'order', to_save[str(book.book_id)])
                counter += 1
                # if order different from before -> shelf.last_modified = datetime.utcnow()
            try:
                ub.session.commit()
            except (OperationalError, InvalidRequestError) as e:
                ub.session.rollback()
                log.error_or_exception("Settings Database error: {}".format(e))
                flash(_("उफ्! डाटाबेस त्रुटि: %(error)s.", error=e.orig), category="error")

        result = list()
        if shelf:
            result = calibre_db.session.query(db.Books) \
                .join(ub.BookShelf, ub.BookShelf.book_id == db.Books.id, isouter=True) \
                .add_columns(calibre_db.common_filters().label("visible")) \
                .filter(ub.BookShelf.shelf == shelf_id).order_by(ub.BookShelf.order.asc()).all()
        return render_title_template('shelf_order.html', entries=result,
                                     title=_("Change order of Shelf: '%(name)s'", name=shelf.name),
                                     shelf=shelf, page="shelforder")
    else:
        abort(404)


def check_shelf_edit_permissions(cur_shelf):
    if not cur_shelf.is_public and not cur_shelf.user_id == int(current_user.id):
        log.error("User {} not allowed to edit shelf: {}".format(current_user.id, cur_shelf.name))
        return False
    if cur_shelf.is_public and not current_user.role_edit_shelfs():
        log.info("User {} not allowed to edit public shelves".format(current_user.id))
        return False
    return True


def check_shelf_view_permissions(cur_shelf):
    if cur_shelf.is_public:
        return True
    if current_user.is_anonymous or cur_shelf.user_id != current_user.id:
        log.error("User is unauthorized to view non-public shelf: {}".format(cur_shelf.name))
        return False
    return True


# if shelf ID is set, we are editing a shelf
def create_edit_shelf(shelf, page_title, page, shelf_id=False):
    sync_only_selected_shelves = current_user.kobo_only_shelves_sync
    # calibre_db.session.query(ub.Shelf).filter(ub.Shelf.user_id == current_user.id).filter(ub.Shelf.kobo_sync).count()
    if request.method == "POST":
        to_save = request.form.to_dict()
        if not current_user.role_edit_shelfs() and to_save.get("is_public") == "on":
            flash(_("माफ गर्नुहोस्, तपाईंलाई सार्वजनिक शेल्फ सिर्जना गर्न अनुमति छैन"), category="error")
            return redirect(url_for('web.index'))
        is_public = 1 if to_save.get("is_public") == "on" else 0
        if config.config_kobo_sync:
            shelf.kobo_sync = True if to_save.get("kobo_sync") else False
            if shelf.kobo_sync:
                ub.session.query(ub.ShelfArchive).filter(ub.ShelfArchive.user_id == current_user.id).filter(
                    ub.ShelfArchive.uuid == shelf.uuid).delete()
                ub.session_commit()
        shelf_title = to_save.get("title", "")
        if check_shelf_is_unique(shelf_title, is_public, shelf_id):
            shelf.name = shelf_title
            shelf.is_public = is_public
            if not shelf_id:
                shelf.user_id = int(current_user.id)
                ub.session.add(shelf)
                shelf_action = "created"
                flash_text = _("शेल्फ %(title)s  को सिर्जना ", title=shelf_title)
            else:
                shelf_action = "changed"
                flash_text = _("शेल्फ %(title)s परिवर्तन भयो", title=shelf_title)
            try:
                ub.session.commit()
                log.info("Shelf {} {}".format(shelf_title, shelf_action))
                flash(flash_text, category="success")
                return redirect(url_for('shelf.show_shelf', shelf_id=shelf.id))
            except (OperationalError, InvalidRequestError) as ex:
                ub.session.rollback()
                log.error_or_exception(ex)
                log.error_or_exception("Settings Database error: {}".format(ex))
                flash(_("उफ्! डाटाबेस त्रुटि: %(error)s.", error=ex.orig), category="error")
            except Exception as ex:
                ub.session.rollback()
                log.error_or_exception(ex)
                flash(_("एउटा त्रुटि थियो"), category="error")
    return render_title_template('shelf_edit.html',
                                 shelf=shelf,
                                 title=page_title,
                                 page=page,
                                 kobo_sync_enabled=config.config_kobo_sync,
                                 sync_only_selected_shelves=sync_only_selected_shelves)


def check_shelf_is_unique(title, is_public, shelf_id=False):
    if shelf_id:
        ident = ub.Shelf.id != shelf_id
    else:
        ident = true()
    if is_public == 1:
        is_shelf_name_unique = ub.session.query(ub.Shelf) \
                                   .filter((ub.Shelf.name == title) & (ub.Shelf.is_public == 1)) \
                                   .filter(ident) \
                                   .first() is None

        if not is_shelf_name_unique:
            log.error("A public shelf with the name '{}' already exists.".format(title))
            flash(_("'%(title)s' नामको सार्वजनिक शेल्फ पहिले नै अवस्थित छ।", title=title),
                  category="error")
    else:
        is_shelf_name_unique = ub.session.query(ub.Shelf) \
                                   .filter((ub.Shelf.name == title) & (ub.Shelf.is_public == 0) &
                                           (ub.Shelf.user_id == int(current_user.id))) \
                                   .filter(ident) \
                                   .first() is None

        if not is_shelf_name_unique:
            log.error("A private shelf with the name '{}' already exists.".format(title))
            flash(_("'%(title)s' नामको निजी शेल्फ पहिले नै अवस्थित छ।", title=title),
                  category="error")
    return is_shelf_name_unique


def delete_shelf_helper(cur_shelf):
    if not cur_shelf or not check_shelf_edit_permissions(cur_shelf):
        return False
    shelf_id = cur_shelf.id
    ub.session.delete(cur_shelf)
    ub.session.query(ub.BookShelf).filter(ub.BookShelf.shelf == shelf_id).delete()
    ub.session.add(ub.ShelfArchive(uuid=cur_shelf.uuid, user_id=cur_shelf.user_id))
    ub.session_commit("successfully deleted Shelf {}".format(cur_shelf.name))
    return True


def change_shelf_order(shelf_id, order):
    result = calibre_db.session.query(db.Books).outerjoin(db.books_series_link,
                                                          db.Books.id == db.books_series_link.c.book)\
        .outerjoin(db.Series).join(ub.BookShelf, ub.BookShelf.book_id == db.Books.id) \
        .filter(ub.BookShelf.shelf == shelf_id).order_by(*order).all()
    for index, entry in enumerate(result):
        book = ub.session.query(ub.BookShelf).filter(ub.BookShelf.shelf == shelf_id) \
            .filter(ub.BookShelf.book_id == entry.id).first()
        book.order = index
    ub.session_commit("Shelf-id:{} - Order changed".format(shelf_id))


def render_show_shelf(shelf_type, shelf_id, page_no, sort_param):
    shelf = ub.session.query(ub.Shelf).filter(ub.Shelf.id == shelf_id).first()

    # check user is allowed to access shelf
    if shelf and check_shelf_view_permissions(shelf):
        if shelf_type == 1:
            # order = [ub.BookShelf.order.asc()]
            if sort_param == 'pubnew':
                change_shelf_order(shelf_id, [db.Books.pubdate.desc()])
            if sort_param == 'pubold':
                change_shelf_order(shelf_id, [db.Books.pubdate])
            if sort_param == 'abc':
                change_shelf_order(shelf_id, [db.Books.sort])
            if sort_param == 'zyx':
                change_shelf_order(shelf_id, [db.Books.sort.desc()])
            if sort_param == 'new':
                change_shelf_order(shelf_id, [db.Books.timestamp.desc()])
            if sort_param == 'old':
                change_shelf_order(shelf_id, [db.Books.timestamp])
            if sort_param == 'authaz':
                change_shelf_order(shelf_id, [db.Books.author_sort.asc(), db.Series.name, db.Books.series_index])
            if sort_param == 'authza':
                change_shelf_order(shelf_id, [db.Books.author_sort.desc(),
                                              db.Series.name.desc(),
                                              db.Books.series_index.desc()])
            page = "shelf.html"
            pagesize = 0
        else:
            pagesize = sys.maxsize
            page = 'shelfdown.html'

        result, __, pagination = calibre_db.fill_indexpage(page_no, pagesize,
                                                           db.Books,
                                                           ub.BookShelf.shelf == shelf_id,
                                                           [ub.BookShelf.order.asc()],
                                                           True, config.config_read_column,
                                                           ub.BookShelf, ub.BookShelf.book_id == db.Books.id)
        # delete chelf entries where book is not existent anymore, can happen if book is deleted outside calibre-web
        wrong_entries = calibre_db.session.query(ub.BookShelf) \
            .join(db.Books, ub.BookShelf.book_id == db.Books.id, isouter=True) \
            .filter(db.Books.id == None).all()
        for entry in wrong_entries:
            log.info('Not existing book {} in {} deleted'.format(entry.book_id, shelf))
            try:
                ub.session.query(ub.BookShelf).filter(ub.BookShelf.book_id == entry.book_id).delete()
                ub.session.commit()
            except (OperationalError, InvalidRequestError) as e:
                ub.session.rollback()
                log.error_or_exception("Settings Database error: {}".format(e))
                flash(_("उफ्! डाटाबेस त्रुटि: %(error)s.", error=e.orig), category="error")

        return render_title_template(page,
                                     entries=result,
                                     pagination=pagination,
                                     title=_("शेल्फ: '%(name)s'", name=shelf.name),
                                     shelf=shelf,
                                     page="shelf")
    else:
        flash(_("सेल्फ खोल्दा त्रुटि भयो। शेल्फ अवस्थित छैन वा पहुँचयोग्य छैन"), category="error")
        return redirect(url_for("web.index"))
