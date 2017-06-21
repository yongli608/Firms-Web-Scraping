from utils import InputTable
#from utils import WebsiteRawTokensWithTaggedBizRegion
from utils import GooglePlacesAccess
from utils import JsonSink
import json
import os

class Stage1(object):
    def __init__(self):
        self.stage1_output_intermediate_filename = 'sink.json.intermediate'
        self.stage1_output_final_filename = 'stage1.json'

        self.mygoogle = GooglePlacesAccess()
        self.mytable = InputTable(places_api = self.mygoogle)
        self.mysink = JsonSink(file_name = self.stage1_output_intermediate_filename)

    def post_fix(self):
        """
        The intermediate file was designed so that you could easily append json examples to it
        without having to worry about any outer containers or metadata

        So we then fix up the file so it's proper json and can be run by NextML
        """
        with open(self.stage1_output_intermediate_filename, 'r') as intermediate:
            final_output = [json.loads(row) for row in intermediate]

        import ipdb
        ipdb.set_trace()
        with open(self.stage1_output_final_filename, 'w') as final:
            json.dump(final_output, final, ensure_ascii=False)

    def run(self):
        """
        Implements basic ingest and output to follow on Biz, Owner Information stages
        Assumes an input.csv exists with columns for 'Business Name' and 'Region'
        """
        self.mytable.push(getter=self.mytable.feature_getter,
                          sink=self.mysink)

        assert os.path.isfile(self.stage1_output_filename), "Stage1 did not produce an output file!"

        return True
