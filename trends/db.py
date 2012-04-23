import logging

import redis
import redis.exceptions
import MySQLdb

import config
import log

class Db(object):

    db_mem = None
    db_mem_posts = None
    db_disk_posts = None
    retries = 360
    retry_wait = 10 
    
    def __init__(self):
        c = config.Config()
        self.config = c.cfg
        self.log = logging.getLogger('db')
        
    def setup_redis_loop(self):
        """Setup connection to Redis until it succeeds"""
        retry = 0
        while True:
            try:
                self.setup_redis()
            except exception.DbError:
                retry += 1
                if retry <= self.retries:
                    time.sleep(self.retry_wait)
                else:
                    break
            break
    
    def setup_redis(self):
        # connections to Redis
        host = self.config.get('redis', 'host'),
        port = self.config.getint('redis', 'port'),
        try:
            self.db_mem = redis.Redis(host=host, port=port, db=0)
            self.db_mem_posts = redis.Redis(
                host=host, port=port, db=1)
        except redis.exceptions.AuthenticationError:
            self.log.error('Problem to authenticate on Redis host %s', host)
            raise exceptions.DbError()
        except redis.exceptions.ConnectionError:
            self.log.error('Problem to connect to Redis host %s', host)
            raise exceptions.DbError()
    
    def setup_mysql_loop(self):
        """Setup connection to Redis until it succeeds"""
        while True:
            try:
                self.setup_mysql()
            except exceptions.DbError:
                time.sleep(10)
                continue
            break

    def setup_mysql(self):
        # connections to MySQL
        user = self.config.get('mysql', 'user')
        password = self.config.get('mysql', 'password')
        db = self.config.get('mysql', 'db')
        try:
            self.db_disk_posts = MySQLdb.connect(
                user=user, passwd=password, db=db,
                use_unicode=True, charset='utf8')
            self.db_cursor = self.db_disk_posts.cursor()
        except MySQLdb.Error:
            self.log.error('Problem to connect to MySQL host %s', host)
            raise exceptions.DbError()

    def redis_cmd(self, cmd, *args):
        redis_command(0, cmd, args)

    def redis_cmd_db_1(self, cmd, *args):
        redis_command(1, cmd, args)

    def redis_command(self, db, cmd, *args):
        if db == 0:
            dbr = self.db_mem
        else:
            dbr = self.db_mem_posts
        while True:
            try:
                return getattr(dbr, cmd)(args)
            except redis.exceptions.ConnectionError:
                self.log.error('Redis cmd %s connection error', cmd)
                # reconnect
                self.setup_redis_loop()
            except AttributeError:
                self.log.error('Redis cmd %s does not exist', cmd)
                break
            except Exception:
                self.log.exception('Redis cmd %s failed', cmd)
                break

    def mysql_cmd(self, cmd, sql, writer, *args):
        while True:
            try:
                getattr(self.db_cursor, cmd)(sql, args)
                if writer:
                    self.db_disk_posts.commit()
                else:
                    return self.db_cursor.fetchall() 
            except (MySQLdb.OperationalError, MySQLdb.InternalError):
                self.log.error('MySQL cmd %s DB error', cmd)
                # reconnect
                self.setup_mysql_loop()
            except MySQLdb.Error:
                self.log.error('MySQL cmd %s sql %s failed', cmd, sql)
                break
            except AttributeError:
                self.log.error('MySQL cmd %s does not exist', cmd)
                break
            except Exception:
                self.log.exception('MySQL cmd %s sql %s failed', cmd, sql)
                break

    def get_persons(self):
        """
        Get list of persons from db
        """
        key = 'persons'
        names = self.redis_cmd('lrange', 'persons', 0, -1)
        persons = []
        for n in names:
            s = n.split(':')
            person = {}
            person['id'] = int(s[0])
            person['first_name'] = s[1] 
            person['name'] = s[2] 
            person['nickname'] = s[3] 
            person['group'] = int(s[4])
            person['words'] = json.loads(s[5])
            person['posts_count'] = 0
            person['rel'] = {}
            persons.append(person)

        return persons

    def set_persons(self):
        """
        Set list of persons in db
        """
        key = 'persons'
        self.redis_cmd('delete', key)
        with open('names.txt', 'r') as f:
            for line in f:
                self.redis_cmd('rpush', key, line.rstrip('\n'))

 