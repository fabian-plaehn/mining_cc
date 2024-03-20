#from mining_cc.deamon.flask_deamon import run
from mining_cc.deamon.deamon_class import Deamon

if __name__ == '__main__':
    deamon = Deamon()
    deamon.run()