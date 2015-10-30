import logging
import os
import tempfile
import time
import unittest2 as unittest

import redis
from mock import patch, call, Mock
import MySQLdb

import trends.db as db
import trends.exceptions as exceptions

logging.basicConfig(filename='log_test_db.txt',level=logging.DEBUG)

class DbTest(unittest.TestCase):

    def setUp(self):
        self.db = db.Db()
        self.cfg_mysql_host = 'test_mysql_host'
        self.cfg_mysql_user = 'test_mysql_user'
        self.cfg_mysql_password = 'test_mysql_password'
        self.cfg_mysql_db = 'test_mysql_db'
        self.cfg_twitter_userid = 'test_twitter_userid'
        self.cfg_twitter_password = 'test_twitter_password'
        self.cfg_redis_host = 'test_redis_host'
        self.cfg_redis_port = 1
        self.cfg_rabbitmq_host = 'test_rabbitmq_host'
        self.cfg_rabbitmq_userid = 'test_rabbitmq_userid'
        self.cfg_rabbitmq_password = 'test_rabbitmq_password'

    @patch('redis.Redis')
    def test_setup_redis(self, redis_class_mock):
        redis_instance = 'test_redis_instance'
        redis_class_mock.return_value = redis_instance
        self.db.setup_redis()
        call_args_list = redis_class_mock.call_args_list
        expected = [call(host = self.cfg_redis_host,
                         port = self.cfg_redis_port, db = 0),
                    call(host = self.cfg_redis_host,
                         port = self.cfg_redis_port, db = 1)]
        self.assertListEqual(call_args_list, expected)
        self.assertEqual(call_args_list, expected)
        self.assertIs(self.db.db_mem, redis_instance)
        self.assertIs(self.db.db_mem_posts, redis_instance)

    @patch.object(MySQLdb, 'connect')
    def test_setup_mysql(self, connect_mock):
        mock = Mock()
        connect_mock.return_value = mock
        cursor = 'test_cursor'
        mock.cursor.return_value = cursor
        self.db.setup_mysql()
        connect_mock.assert_called_once_with(host=self.cfg_mysql_host,
            passwd=self.cfg_mysql_password,
            charset='utf8', db=self.cfg_mysql_db, user=self.cfg_mysql_user,
            use_unicode=True)
        self.assertTrue(mock.cursor.called)
        self.assertIs(self.db.db_disk_posts, mock)
        self.assertIs(self.db.db_cursor, cursor)

    @patch.object(MySQLdb, 'connect')
    def test_setup_mysql_connect_error(self, connect_mock):
        connect_mock.side_effect = MySQLdb.Error()
        self.assertRaises(exceptions.DbError, self.db.setup_mysql)

    @patch.object(db.Db, 'setup_mysql')
    def test_setup_mysql_loop(self, setup_mysql_mock):
        self.db.retries = 1
        self.db.setup_mysql_loop()
        self.assertTrue(setup_mysql_mock.called)

    @patch.object(db.Db, 'setup_mysql')
    @patch.object(time, 'sleep')
    def test_setup_mysql_loop_db_error(self, time_sleep_mock, setup_mysql_mock):
        self.db.retries = 2
        self.db.retry_wait = 0.1
        setup_mysql_mock.side_effect = exceptions.DbError() 
        self.assertRaises(exceptions.DbError, self.db.setup_mysql_loop) 
        self.assertEqual(setup_mysql_mock.call_count, 2)
        self.assertEqual(time_sleep_mock.call_count, 2)

    @patch.object(db.Db, 'db_mem')
    def test_redis_command_db_0(self, db_mem_mock):
        db_mem_mock.get.return_value = 'test'
        r = self.db.redis_command(0, 'get', 'test_key')
        db_mem_mock.get.assert_called_once_with('test_key')
        self.assertEqual(r, 'test')

    @patch.object(db.Db, 'db_mem_posts')
    def test_redis_command_db_1(self, db_mem_posts_mock):
        db_mem_posts_mock.get.return_value = 'test'
        r = self.db.redis_command(1, 'get', 'test_key')
        db_mem_posts_mock.get.assert_called_once_with('test_key')
        self.assertEqual(r, 'test')

    @patch.object(db.Db, 'db_mem')
    def test_redis_command_redis_error(self, db_mem_mock):
        self.db.cmd_retries = 2
        self.db.cmd_retry_wait = 0.1
        db_mem_mock.get.side_effect = redis.exceptions.RedisError()
        self.assertRaises(exceptions.DbError,
            self.db.redis_command,
            0, 'get', 'test_key')
        db_mem_mock.get.assert_called_with('test_key')
        self.assertEqual(db_mem_mock.get.call_count, 2)

    @patch.object(db.Db, 'db_mem')
    def test_redis_command_attribute_error(self, db_mem_mock):
        db_mem_mock.get.side_effect = AttributeError()
        self.assertRaises(exceptions.DbError,
            self.db.redis_command,
            0, 'get', 'test_key')
        db_mem_mock.get.assert_called_once_with('test_key')

    @patch.object(db.Db, 'db_disk_posts')
    @patch.object(db.Db, 'db_cursor')
    def test_mysql_command(self, db_cursor_mock, db_disk_posts_mock):
        db_cursor_mock.fetchall.return_value = ((1,2,3))
        r = self.db.mysql_command('execute', 'test_sql', False, False,
            'test_arg')
        db_cursor_mock.execute.assert_called_once_with(
            'test_sql', ('test_arg',))
        self.assertTrue(db_cursor_mock.fetchall.called)
        self.assertFalse(db_disk_posts_mock.commit.called)
        self.assertEqual(r, ((1,2,3)))

    @patch.object(db.Db, 'db_disk_posts')
    @patch.object(db.Db, 'db_cursor')
    def test_mysql_command_writer(self, db_cursor_mock, db_disk_posts_mock):
        db_cursor_mock.execute.return_value = 2
        r = self.db.mysql_command('execute', 'test_sql', True, True,
            'test_arg')
        db_cursor_mock.execute.assert_called_once_with(
            'test_sql', ('test_arg',))
        self.assertTrue(db_disk_posts_mock.commit.called)
        self.assertEqual(r, 2)

    @patch.object(db.Db, 'setup_mysql_loop')
    @patch.object(db.Db, 'db_cursor')
    def test_mysql_command_operational_error(self, db_cursor_mock,
            setup_mysql_loop_mock):
        db_cursor_mock.execute.side_effect = MySQLdb.OperationalError()
        setup_mysql_loop_mock.side_effect = exceptions.DbError()
        self.assertRaises(exceptions.DbError,
            self.db.mysql_command,
            'execute', 'test_sql', True, True, 'test_arg')
        db_cursor_mock.execute.assert_called_once_with(
            'test_sql', ('test_arg',))

    @patch.object(db.Db, 'setup_mysql_loop')
    @patch.object(db.Db, 'db_cursor')
    def test_mysql_command_internal_error(self, db_cursor_mock,
            setup_mysql_loop_mock):
        db_cursor_mock.execute.side_effect = MySQLdb.InternalError()
        setup_mysql_loop_mock.side_effect = exceptions.DbError()
        self.assertRaises(exceptions.DbError,
            self.db.mysql_command,
            'execute', 'test_sql', True, 'test_arg')
        db_cursor_mock.execute.assert_called_once_with(
            'test_sql', ('test_arg',))

    @patch.object(db.Db, 'db_cursor')
    def test_mysql_command_internal_error(self, db_cursor_mock):
        self.db.cmd_retries = 2
        self.db.cmd_retry_wait = 0.1
        db_cursor_mock.execute.side_effect = MySQLdb.Error()
        self.assertRaises(exceptions.DbError,
            self.db.mysql_command,
            'execute', 'test_sql', True, True, 'test_arg')
        db_cursor_mock.execute.assert_called_with(
            'test_sql', ('test_arg',))
        self.assertEqual(db_cursor_mock.execute.call_count, 2)

    @patch.object(db.Db, 'db_cursor')
    def test_mysql_command_attribute_error(self, db_cursor_mock):
        db_cursor_mock.execute.side_effect = AttributeError()
        self.assertRaises(exceptions.DbError,
            self.db.mysql_command,
            'execute', 'test_sql', True, True, 'test_arg')
        db_cursor_mock.execute.assert_called_with(
            'test_sql', ('test_arg',))

    @patch.object(db.Db, 'redis_cmd')
    def test_get_persons(self, redis_cmd_mock):
        data = (('1:test_first_name_1:test_name_1:test_nickname_1:2:'\
                 '[\"test_word_1\", \"test_word_2\"]'),
                ('3:test_first_name_2:test_name_2:test_nickname_2:4:'\
                 '[\"test_word_3\", \"test_word_4\"]'))
        redis_cmd_mock.return_value = data
        r = self.db.get_persons()
        self.assertDictEqual(r[0],
            {'id': 1, 'first_name': 'test_first_name_1', 'name': 'test_name_1',
             'nickname': 'test_nickname_1', 'group': 2, 'rel': {},
             'posts_count': 0,
             'words': ['test_word_1', 'test_word_2']})
        self.assertDictEqual(r[1],
            {'id': 3, 'first_name': 'test_first_name_2', 'name': 'test_name_2',
             'nickname': 'test_nickname_2', 'group': 4, 'rel': {},
             'posts_count': 0,
             'words': ['test_word_3', 'test_word_4']})
        redis_cmd_mock.assert_called_once_with('lrange', 'persons', 0, -1)

    @patch.object(db.Db, 'redis_cmd')
    def test_set_persons(self, redis_cmd_mock):
        with open('names.txt', 'w') as f:
            f.write('test_name_1\ntest_name_2\n')
        self.db.set_persons()
        self.assertEqual(redis_cmd_mock.call_args_list,
            [call('delete', 'persons'), call('rpush', 'persons', 'test_name_1'),
             call('rpush', 'persons', 'test_name_2')])
        os.remove('names.txt')

    @patch.object(db.Db, 'set')
    @patch.object(db.Db, 'sql_write')
    def test_set_post_redis(self, sql_write_mock, set_mock):
        post_id = 2
        value = 'test_value'
        self.db.posts_tid = 1
        self.db.set_post(post_id, value)
        set_mock.assert_called_once_with('post:%d' % (post_id), value, db=1)
        self.assertFalse(sql_write_mock.called)

    @patch.object(db.Db, 'set')
    @patch.object(db.Db, 'sql_write')
    def test_set_post_sql(self, sql_write_mock, set_mock):
        post_id = 1
        value = 'test_value'
        self.db.posts_tid = 2
        self.db.set_post(post_id, value)
        sql = 'insert into tp_post(post_id, post) values(%s, %s)'\
              'on duplicate key update post=%s'
        sql_write_mock.assert_called_once_with(sql, post_id, value, value)
        self.assertFalse(set_mock.called)

if __name__ == '__main__':
    unittest.main()
