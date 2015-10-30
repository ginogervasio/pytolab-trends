#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import logging
import time

import redis
import redis.exceptions
import MySQLdb

import config
import data
import exceptions
import log

class Db(object):

    db_mem = None
    db_mem_posts = None
    db_disk_posts = None
    db_cursor = None
    retries = 360
    retry_wait = 10
    cmd_retries = 10
    cmd_retry_wait = 10

    def __init__(self):
        c = config.Config()
        self.config = c.cfg
        self.log = logging.getLogger('db')
        self.dir_root = self.config.get('trends', 'root')

    def setup(self):
        """
        Setup the connection to Redis DB and to MySQL DB.
        """
        self.setup_redis()
        self.setup_mysql_loop()
        # Get marker to know if a post id is in Redis or MySQL.
        self.posts_tid = int(self.get('posts_tid'))

    def setup_redis(self):
        """Connections to Redis."""
        host = self.config.get('redis', 'host')
        port = self.config.getint('redis', 'port')
        self.db_mem = redis.Redis(host=host, port=port, db=0)
        self.db_mem_posts = redis.Redis(host=host, port=port, db=1)

    def setup_mysql_loop(self):
        """Setup connection to Redis until it succeeds"""
        retry = 0
        while retry < self.retries:
            try:
                self.setup_mysql()
                return
            except exceptions.DbError:
                if retry < self.retries:
                    time.sleep(self.retry_wait)
                retry += 1
        self.log.error(
            '%d retries to connect to MySQL failed', self.retries)
        raise exceptions.DbError()

    def setup_mysql(self):
        """Setup connections to MySQL"""
        user = self.config.get('mysql', 'user')
        password = self.config.get('mysql', 'password')
        db = self.config.get('mysql', 'db')
        host = self.config.get('mysql', 'host')
        try:
            self.db_disk_posts = MySQLdb.connect(host=host,
                user=user, passwd=password, db=db,
                use_unicode=True, charset='utf8')
            self.db_cursor = self.db_disk_posts.cursor()
        except MySQLdb.Error:
            self.log.error('Problem to connect to MySQL host %s', host)
            raise exceptions.DbError()

    def redis_cmd(self, cmd, *args):
        """Redis command to DB index 0"""
        return self.redis_command(0, cmd, *args)

    def redis_cmd_db_1(self, cmd, *args):
        """Redis command to DB index 1"""
        return self.redis_command(1, cmd, *args)

    def redis_command(self, db, cmd, *args):
        """Command to Redis.

        Try cmd_retries times.
        """
        if db == 0:
            dbr = self.db_mem
        else:
            dbr = self.db_mem_posts
        retry = 0
        while retry < self.cmd_retries:
            try:
                return getattr(dbr, cmd)(*args)
            except redis.exceptions.RedisError:
                self.log.error('Redis cmd %s error', cmd)
                retry += 1
                if retry <= self.cmd_retries:
                    time.sleep(self.cmd_retry_wait)
            except AttributeError:
                self.log.error('Redis cmd %s does not exist', cmd)
                raise exceptions.DbError()
        raise exceptions.DbError()

    def get(self, key, db=0):
        if db == 0:
            return self.redis_cmd('get', key)
        else:
            return self.redis_cmd_db_1('get', key)

    def set(self, key, value, db=0):
        if db == 0:
            return self.redis_cmd('set', key, value)
        else:
            return self.redis_cmd_db_1('set', key, value)

    def delete(self, key):
        return self.redis_cmd('delete', key)

    def exists(self, key):
        return self.redis_cmd('exists', key)

    def incr(self, key):
        return self.redis_cmd('incr', key)

    def rpush(self, key, value):
        return self.redis_cmd('rpush', key, value)

    def lrange(self, key, start, stop):
        return self.redis_cmd('lrange', key, start, stop)

    def lset(self, key, index, value):
        return self.redis_cmd('lset', key, index, value)

    def lindex(self, key, index):
        return self.redis_cmd('lindex', key, index)

    def mysql_command(self, cmd, sql, writer, commit, *args):
        """Command to MySQL.

        Try cmd_retries times."""
        retry = 0
        while retry < self.cmd_retries:
            try:
                r = getattr(self.db_cursor, cmd)(sql, args)
                if writer:
                    if commit:
                        self.db_disk_posts.commit()
                    return r
                else:
                    return self.db_cursor.fetchall()
            except (MySQLdb.OperationalError, MySQLdb.InternalError):
                self.log.error('MySQL cmd %s DB error', cmd)
                # reconnect
                self.setup_mysql_loop()
                retry = 0
            except MySQLdb.Error:
                self.log.error('MySQL cmd %s sql %s failed', cmd, sql)
                retry += 1
                if retry <= self.cmd_retries:
                    time.sleep(self.cmd_retry_wait)
            except AttributeError:
                self.log.error('MySQL cmd %s does not exist', cmd)
                raise exceptions.DbError()
        raise exceptions.DbError()

    def sql_read(self, sql, *args):
        """Read command to MySQL."""
        return self.mysql_command('execute', sql, False, False, *args)

    def sql_write(self, sql, *args):
        """Write command to MySQL."""
        return self.mysql_command('execute', sql, True, True, *args)

    def sql_write_no_commit(self, sql, *args):
        """Write command to MySQL but no commit."""
        return self.mysql_command('execute', sql, True, False, *args)

    def sql_commit(self):
        """Commit changes to disk"""
        self.db_disk_posts.commit()

    def set_post(self, post_id, value):
        """Add/Update post value in Redis or MySQL based on posts id marker...
        """
        if post_id >= self.posts_tid:
            self.set('post:%d' % (post_id,), value, db=1)
        else:
            sql = 'insert into tp_post(post_id, post) values(%s, %s)'\
                  'on duplicate key update post=%s'
            self.sql_write(sql, post_id, value, value)

    def get_post(self, post_id):
        """Get post value from Redis or MySQL based on posts id marker...
        """
        if post_id >= self.posts_tid:
            r = self.get('post:%d' % (post_id,), db=1)
        else:
            try:
                sql = 'select post from tp_post where post_id=%s'
                r = self.sql_read(sql, post_id)
            except exceptions.DbError:
                r = None
        return r

    def get_persons(self):
        """
        Get list of persons from db
        """
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
        with open('%s/names.txt' % (self.dir_root), 'r') as f:
            for line in f:
                self.redis_cmd('rpush', key, line.rstrip('\n'))

    def iter_posts(self): 
        post_id_start = 108673
        post_id_end = 8561087
        last_id = post_id_start
        while True:
            sql = 'select post_id, post from tp_post'\
                  ' where post_id > %s and post_id <= %s order by post_id'\
                  ' limit 1000'
            rows = self.sql_read(sql, last_id, post_id_end)
            if not rows:
                break
            last_id = rows[-1][0]
            r = []
            for row in rows:
                d = data.parse_post(row[1])
                d['post_id'] = row[0]
                r.append(d)
            yield r

    def get_person_ids_from_post_id(self, post_id):
        sql = 'select person_id from tp_person_post where post_id = %s'
        rows = self.sql_read(sql, post_id)
        return [row[0] for row in rows]

