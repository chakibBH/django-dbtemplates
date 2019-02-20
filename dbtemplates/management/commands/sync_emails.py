import io
import os
import re
from django.contrib.sites.models import Site
from django.core.management.base import CommandError, BaseCommand
# from django.template.utils import get_app_template_dirs
from django.template.loader import _engine_list

from dbtemplates.models import Template


"""
Mods:
- PEP 3111: raw_input() was renamed to input()
- 'tpl_dirs' is a tuples concatenation,
    to avoid TypeError: DIRS -> tuple(DIRS)
    type(DIRS) is list
    type(app_template_dirs) is tuple
- help message of --ext has been amended
- default value of --override has been set to '1'
- only check for templates listed in settings.TEMPLATES['DIRS']


Eg.:
sync_emails -f -o 1  # FILES_TO_DATABASE
sync_emails -f -o 2  # DATABASE_TO_FILES

"""

ALWAYS_ASK, FILES_TO_DATABASE, DATABASE_TO_FILES = ('0', '1', '2')


# CF line 82
# DIRS = []
# for engine in _engine_list():
#     DIRS.extend(engine.dirs)
# app_template_dirs = get_app_template_dirs('templates')


class Command(BaseCommand):
    help = """
        Synchronise les templates des dossiers listés dans settings.TEMPLATES['DIRS']
        python manage.py sync_mail_templates -f -o 1  # Les Fichiers écrasent les valeur en Base
        python manage.py sync_mail_templates -f -o 2  # Les valeurs en Base écrasent le contenu des Fichiers
        """

    def add_arguments(self, parser):
        parser.add_argument(
            "-e", "--ext",
            dest="ext", action="store", default="html",
            help="extension of the files you want to "
                 "sync with the database [default: html]")
        parser.add_argument(
            "-f", "--force",
            action="store_true", dest="force", default=False,
            help="overwrite existing database templates [default: False]")
        parser.add_argument(
            "-o", "--overwrite",
            action="store", dest="overwrite", default='1',
            help="'0' - ask always, '1' - overwrite database "
                 "templates from template files, '2' - overwrite "
                 "template files from database templates  [default: 1]")
        parser.add_argument(
            "-d", "--delete",
            action="store_true", dest="delete", default=False,
            help="Delete templates after syncing [default: False]")

    def handle(self, **options):
        extension = options.get('ext')
        force = options.get('force')
        overwrite = options.get('overwrite')
        delete = options.get('delete')

        if not extension.startswith("."):
            extension = ".%s" % extension

        try:
            site = Site.objects.get_current()
        except:
            raise CommandError("Please make sure to have the sites contrib "
                               "app installed and setup with a site object")

        # Supprimer car on ne va itérer que sur les dossiers de templates
        # de 'covoiturage'
        # WARNING: type(DIRS) is list  & type(app_template_dirs) is tuple
        # if app_first:
        #     tpl_dirs = app_template_dirs + DIRS
        # else:
        #     tpl_dirs = DIRS + app_template_dirs
        # templatedirs = [d for d in tpl_dirs if os.path.isdir(d)]
        import fnmatch
        DIRS = []
        for engine in _engine_list():
            DIRS.extend(engine.dirs)

        templatedirs = [d for d in DIRS if os.path.isdir(d)]

        for templatedir in templatedirs:
            for dirpath, subdirs, filenames in os.walk(templatedir):

                # On va twitcher en important uniquement les templates d'emails
                if not fnmatch.fnmatch(dirpath, '*/email/*'):
                    continue

                for f in [f for f in filenames if f.endswith(extension) and not f.startswith(".")]:
                    path = os.path.join(dirpath, f)
                    name = path.split(templatedir)[1]
                    if name.startswith('/'):
                        name = name[1:]
                    try:
                        t = Template.on_site.get(name__exact=name)
                    except Template.DoesNotExist:
                        if not force:
                            msg = """\nA '{0}' template doesn't exist in the
                                     database.\nCreate it with '{1}'? (y/[n]):"""
                            confirm = input(msg.format(name, path))
                        if force or confirm.lower().startswith('y'):
                            with io.open(path, encoding='utf-8') as f:
                                t = Template(name=name, content=f.read())
                            t.save()
                            t.sites.add(site)
                    else:
                        while 1:
                            if overwrite == ALWAYS_ASK:
                                confirm = input(
                                    "\n%(template)s exists in the database.\n"
                                    "(1) Overwrite %(template)s with '%(path)s'\n"
                                    "(2) Overwrite '%(path)s' with %(template)s\n"
                                    "Type 1 or 2 or press <Enter> to skip: " %
                                    {'template': t.__repr__(), 'path': path})
                            else:
                                confirm = overwrite
                            if confirm in ('', FILES_TO_DATABASE,
                                           DATABASE_TO_FILES):
                                if confirm == FILES_TO_DATABASE:
                                    with io.open(path, encoding='utf-8') as f:
                                        t.content = f.read()
                                        t.save()
                                        t.sites.add(site)
                                    if delete:
                                        try:
                                            os.remove(path)
                                        except OSError:
                                            raise CommandError(
                                                u"Couldn't delete %s" % path)
                                elif confirm == DATABASE_TO_FILES:
                                    with io.open(path, 'w', encoding='utf-8') as f:
                                        f.write(t.content)
                                    if delete:
                                        t.delete()
                                break

        templates = Template.objects.all()
        for template in templates:
            if template.content:
                try:
                    striped = template.content.replace('\n', '')
                    pouet = re.search(
                        "{% block subject %}(?P<subject>.*){% endblock subject %}(.*){% block html_body %}(?P<body>.*){% endblock html_body %}",
                        striped,
                        re.MULTILINE
                    )
                    if not pouet:
                        raise Exception('Aucun pattern ne correspond')
                    if not template.subject:
                        template.subject = pouet.group('subject')
                    if not template.body:
                        template.body = pouet.group('body')
                    template.save(update_fields=('subject', 'body'))
                except Exception as err:
                    print("erreur à l'import d'un gabarit: {} {}".format(template.name, str(err)))
