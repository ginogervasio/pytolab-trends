import ConfigParser
class Config(object):

    def __init__(self):
        self.read_config()

    def read_config(self):
        """Return config object from config file"""
        self.cfg = ConfigParser.ConfigParser()
        self.cfg.read('trends.cfg')