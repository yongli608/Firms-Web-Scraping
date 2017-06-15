from googleplaces import GooglePlaces, types, lang
from ApiKey import ApiKeys
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import (
        create_engine,
        Column,
        ForeignKey,
        Integer,
        String,
        )
import textacy
import requests
import pandas as pd
import re
import time, datetime
import itertools
import sys
import os
import errno

# DB, walk through http://docs.sqlalchemy.org/en/latest/orm/tutorial.html
#   to get best practices
#
# also see: https://stackoverflow.com/questions/31394998/using-sqlalchemy-to-load-csv-file-into-a-database
# laste comment on best practices for larger files
#   catch is does COPY FROM support upsert type items

# For now let's just use a Panads read from .csv
class InputTable(object):
    """
    Map an input.csv to the project database (helps to track
    businesses processed, input/outputs, etc.)

    WIP: For now we just do a straight read of the input.csv,
    deupe it but that's it.

    Todo: duplicate, upsert to a project
    local database to more easily capture statistics and
    manage input data flow.
    """
    def __init__(self,
                 database_name="input.csv",
                 pushed="pushed.csv",
                 output="output.csv",
                 data_root='./',
                 places_api=None,
                 featurizer=None):
        self.data_root = data_root
        self.places_api = places_api
        self.featurizer = featurizer

        if not self.featurizer:
            self.featurizer = WebsiteBagOfKeyphrases()

        if not os.path.isfile(output): # then create one, note this a basic output file, not production
            csv_output = pd.DataFrame(columns=['Business Name',
                                               'Region',
                                               'Overwrite',
                                               'Associated Agents',
                                               'Associated Products',
                                               'Source Urls',
                                               ])
            csv_output.to_csv(output, index=False, sep='\t')

        if not os.path.isfile(pushed): # then create one
            csv_pushed = pd.DataFrame(columns=['Business Name',
                                               'Region',
                                               'Overwrite'])
            csv_pushed.to_csv(pushed, index=False, sep='\t')

        file_path = os.path.join(self.data_root, database_name)
        if  os.path.isfile(file_path):
            self.table = pd.read_csv(file_path, sep='\t')
            # treat table as a LIFO queue, most recent copy of
            # bussiness name is kept
            self.table.drop_duplicates(subset=['Business Name',
                                               'Region',
                                               'Overwrite'],
                                       keep='last',
                                       inplace=True)
        else:
            raise FileNotFoundError(
                    errno.ENOENT, os.strerror(errno.ENOENT), file_path)

    def timing_pusher(self, business):
        print(datetime.datetime.now()) # entered into call
        print(business['Business Name'], business['Region'])

    def default_pusher(self, business):
        ret = None
        results = self.places_api.get_results(business_name=business['Business Name'],
                                              region=business['Region'],
                                              types=None)
        relevant_places = self.places_api.get_relevant_places(results)
        ret = self.places_api.get_place_websites(relevant_places)
        return ret

    def feature_pusher(self, business, feature_func=None):
        """
        Gets website "features" (keyphrases, text, etc) as well as pulls website
        address. Gathers data for the rest of the system.

        Extract website features, used for follow on human manual check, for
        active learning task training and, finally, for task prediction
        (both task training and prediction happen at the same time under the
        active learning paradigm)
        """
        if not feature_func:
            feature_func = self.featurizer

        def website_features(dict_results, feature_func=feature_func, key='websites'):
            for url in dict_results[key]:
                if url and url != 'None': # todo: fix dict_results from returning 'None'
                    yield {'features': feature_func.get_website_features(url=url),
                           'website': url,
                           'utc_timestamp': str(datetime.datetime.utcnow())}

        results = self.places_api.get_results(business_name=business['Business Name'],
                                              region=business['Region'],
                                              types=None)

        results = self.places_api.get_place_websites(results)
        dict_results = self.places_api.to_dict(results)

        return website_features(dict_results)

    def push(self, pusher=None, output='output.csv', pushed='pushed.csv'):
        """
        Push a given set of output (if not string, then a dataframe)
        downstream in order to collect business information on the input.

        Can use custom `pusher` if an alternative set of logic
        should be used.

        Checks for race conditions (pushing something twice because
        it hasn't completed between calls) against a pushed table by polling
        """

        if pusher == None:
            pusher = self.default_pusher

        keys = ['Business Name', 'Region']

        for index, business in self.table.iterrows():
            # poll on pushed, output this is fast enough I believe
            pushed = pd.read_csv(os.path.join(self.data_root, pushed), sep='\t')
            output = pd.read_csv(os.path.join(self.data_root, output), sep='\t')

            # check that business does not exist in output or pushed by
            # checking keys. Note: There could be race conditions in here
            # but we assume we can poll magnitudes faster than data arrives
            # and we know that within a session that information is never removed.
            # ... so I think we're mostly good here. Probably can't persist
            # queries across shutdown though but that's okay we can redo it for cheap.
            #
            # note: if instead of .csv's we use a database these problems will go away
            # but not needed at this moment to continue development
            if not all(any(output[key] == business[key]) for key in keys) and\
               not all(any(pushed[key] == business[key]) for key in keys):
                # degelate to pusher
                time.sleep(1)
                yield pusher(business) # currently, should be a blocking call, assume pusher rate limits

class WebsiteBagOfKeyphrases(object):
    def __init__(self, n_keyterms=0.05, url=None):
        self.n_keyterms = n_keyterms
        self.url = url

    def reduce_keyphrases(list_keyphrases):
        return itertools.chain.from_iterable((element.split()\
                for element in list_keyphrases))

    def get_text(self, html):
        """
        Copied from NLTK package.
        Remove HTML markup from the given string.

        see: https://stackoverflow.com/questions/26002076/python-nltk-clean-html-not-implemented
        for more details
        """

        # First we remove inline JavaScript/CSS:
        cleaned = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", "", html.strip())
        # Then we remove html comments. This has to be done before removing regular
        # tags since comments can contain '>' characters.
        cleaned = re.sub(r"(?s)<!--(.*?)-->[\n]?", "", cleaned)
        # Next we can remove the remaining tags:
        cleaned = re.sub(r"(?s)<.*?>", " ", cleaned)
        # Finally, we deal with whitespace
        cleaned = re.sub(r"&nbsp;", " ", cleaned)
        cleaned = re.sub(r"\n", " ", cleaned) # added to strip newlines
        cleaned = re.sub(r"  ", " ", cleaned)
        cleaned = re.sub(r"  ", " ", cleaned)
        return cleaned.strip()

    def get_website_features(self, lang="en", url=None, n_keyterms=None):
        if not n_keyterms:
            n_keyterms = self.n_keyterms

        if not url:
            url = self.url

        html = requests.get(url).text
        text = self.get_text(html)

        processed_text = textacy.preprocess.preprocess_text(text,
                                                            lowercase=True,
                                                            no_urls=True,
                                                            no_emails=True,
                                                            no_phone_numbers=True,
                                                            no_currency_symbols=True,
                                                            no_punct=True)

        doc = textacy.Doc(processed_text, lang=lang)

        keyphrases = textacy.keyterms.singlerank(doc, n_keyterms=n_keyterms)

        return [element[0] for element in keyphrases] # use () for generator if desired

# initalize Google Places API
class GooglePlacesAccess(object):
    """
    A simple class to provide access to the GooglePlaces API.

    To rate limit the API calls to Google Places as one call per second
    we require that all users of this class be under the same process
    (as a child or parent thread). This rate limiting will not work under
    multi process processing, only multi threaded.

    todo: implement rate limiting

    Example:

    import utils
    from googleplaces import types

    myg = utils.GooglePlacesAccess()
    business_name = "Fish and Chips"
    region = "London, England"

    ret1 = myg.get_results(business_name=business_name,
                           region='London, England',
                           types=[types.TYPE_FOOD])
    ret2 = myg.get_relevant_places(ret1)
    ret3 = myg.get_place_websites(ret2)
    """
    def __init__(self, key=ApiKeys['Google Places']):
        self.places_api = GooglePlaces(ApiKeys['Google Places'])

    # todo: requires rate limiting
    def get_results(self,
                    business_name,
                    region,
                    radius=20000,
                    types=None):
        location = region
        keyword = business_name

        results = self.places_api.nearby_search(location=location,
                                                keyword=keyword,
                                                radius=radius,
                                                types=types)

        return results

    # todo: requires rate limiting on loop
    def get_place_websites(self, results):
        ret = []
        for place in results.places:
            time.sleep(1) # note: when rate limitating is implemented, no longer needed

            place.get_details() # side effect, calls Google API
            ret.append(place)

        return ret

    def to_dict(self, relevant_places):
        ret = {'websites':[], 'urls':[]}
        for place in relevant_places:
            ret['websites'].append(place.website)
            ret['urls'].append(place.url)

        return ret

"""
Example usage:

    mygoogle = utils.GooglePlacesAccess()
    mytable = utils.InputTable(places_api=mygoogle)
    # returns per row associated websites to a given business in InputTable
    k = list(mytable.push())

    # do something interesting with `k`, like feed it to MTurk/Crowdflower or
    # to an active online classifier...
"""
