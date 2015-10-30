#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import logging
import os
import time
import unittest2 as unittest

from mock import patch, call

import trends.db as db
import trends.trends as trends
import trends.exceptions as exceptions
    
logging.basicConfig(filename='log_test_tweets.txt',level=logging.DEBUG)

class Test(unittest.TestCase):

    def setUp(self):
        self.trends = trends.Trends('trends.pid')
    
    @patch.object(db.Db, 'set')
    @patch.object(db.Db, 'exists')
    @patch.object(db.Db, 'get_persons')
    @patch.object(db.Db, 'set_persons')
    @patch.object(db.Db, 'setup')
    def test_setup_db(self, setup_mock, set_persons_mock, get_persons_mock,
            exists_mock, set_mock):
        rv = 1
        get_persons_mock.return_value = rv
        key = 'nextPostId'
        self.trends.setup_db()
        self.assertTrue(setup_mock.called)
        self.assertTrue(set_persons_mock.called)
        self.assertTrue(get_persons_mock.called)
        self.trends.persons = rv
        exists_mock.assert_called_once_with(key)

    @patch.object(db.Db, 'set')
    @patch.object(db.Db, 'exists')
    @patch.object(db.Db, 'get_persons')
    @patch.object(db.Db, 'set_persons')
    @patch.object(db.Db, 'setup')
    def test_setup_db_key_not_exist(self, setup_mock, set_persons_mock,
            get_persons_mock, exists_mock, set_mock):
        exists_mock.return_value = False
        key = 'nextPostId'
        self.trends.setup_db()
        set_mock.assert_called_once_with(key, 0)

    @patch.object(time, 'time')
    @patch.object(trends.Trends, 'fill_stats')
    @patch.object(db.Db, 'get')
    @patch.object(db.Db, 'exists')
    def test_update_stats_key_exists(self, exists_mock, get_mock,
            fill_stats_mock, time_mock):
        exists_mock.return_value = True
        t = 1.1
        get_mock.return_value = t
        time_mock.return_value = t + 3600
        key = 'statsLastUpdate'
        self.trends.db = db.Db()
        self.trends.update_stats()
        get_mock.assert_called_once_with(key)
        fill_stats_mock.assert_called_once_with(2)
        self.assertEqual(self.trends.stats_last_update, int(t))

    @patch.object(time, 'time')
    @patch.object(trends.Trends, 'fill_stats')
    @patch.object(db.Db, 'set')
    @patch.object(db.Db, 'exists')
    def test_update_stats_key_not_exists(self, exists_mock, set_mock,
            fill_stats_mock, time_mock):
        exists_mock.return_value = False
        t = 1339987262.1
        time_mock.return_value = t
        self.trends.db = db.Db()
        self.trends.update_stats()
        fill_stats_mock.assert_called_once_with(1)
        self.assertEqual(self.trends.stats_last_update, 1339984800)
        set_mock.assert_called_once_with('statsFirstUpdate', 1339984800)
    
    @patch.object(db.Db, 'lset')
    @patch.object(db.Db, 'lindex')
    def test_update_person_stats_first_person_none(self, lindex_mock,
            lset_mock):
        self.trends.db = db.Db()
        person = {'id': 1}
        key = 'person:%d:posts_count' % (person['id'])
        lindex_mock.return_value = 1
        self.trends.first_person = None
        self.trends.update_person_stats(person)
        lindex_mock.assert_called_once_with(key, -1)
        lset_mock.assert_called_once_with(key, -1, '2')
        self.assertIs(self.trends.first_person, person)

    def lindex(self, key, value):
        if key == 'person:2:posts_count':
            return 1
        else:
            d = {'2': 2, '3': 3}
            return json.dumps(d)

    @patch.object(db.Db, 'lset')
    @patch.object(db.Db, 'lindex', lindex)
    def test_update_person_stats(self, lset_mock):
        self.trends.db = db.Db()
        person = {'id': 2}
        posts_count_key = 'person:%d:posts_count' % (person['id'])
        rel_key = 'person:1:rel'
        self.trends.first_person = {'id': 1}
        self.trends.update_person_stats(person)
        self.assertEqual(lset_mock.call_args_list,
            [call(posts_count_key, -1, '2'),
             call(rel_key, -1, json.dumps({'2': 3, '3': 3}))])

    @patch.object(db.Db, 'set')
    @patch.object(db.Db, 'rpush')
    def test_fill_stats(self, rpush_mock, set_mock):
        periods = 2
        self.trends.persons = [{'id': 2}, {'id': 3}]
        self.trends.stats_last_update = 0
        self.trends.db = db.Db()
        self.trends.fill_stats(periods)
        self.assertEqual(rpush_mock.call_args_list,
            [call('person:2:posts_count', 0),
             call('person:2:rel', json.dumps({})),
             call('person:3:posts_count', 0),
             call('person:3:rel', json.dumps({})),
             call('person:2:posts_count', 0),
             call('person:2:rel', json.dumps({})),
             call('person:3:posts_count', 0),
             call('person:3:rel', json.dumps({}))])
        self.assertEqual = self.trends.stats_last_update = 7200
        set_mock.assert_called_once_with('statsLastUpdate', 7200)
    
    @patch.object(db.Db, 'incr')
    @patch.object(db.Db, 'set_post')
    @patch.object(db.Db, 'rpush')
    def test_process_post_names_not_found(self, rpush_mock, set_post_mock,
            incr_mock):
        self.trends.persons = [
            {'name': 'name_1', 'first_name': 'first_name_1',
             'nickname': 'nickname_1', 'id': 2, 'words': ()},
            {'name': 'name_2', 'first_name': 'first_name_2',
             'nickname': 'nickname_2', 'id': 2, 'words': ()}]
        self.trends.db = db.Db()
        self.trends.stats_last_update = 0
        post = {'text': 'test'}
        self.trends.process_post(post)
        self.assertFalse(rpush_mock.called)
        self.assertFalse(set_post_mock.called)
        self.assertFalse(incr_mock.called)

    @patch.object(db.Db, 'incr')
    @patch.object(db.Db, 'set_post')
    @patch.object(db.Db, 'rpush')
    def test_process_post_text_no_fr(self, rpush_mock, set_post_mock,
            incr_mock):
        self.trends.db = db.Db()
        self.trends.stats_last_update = 0
        post = {'text': 'par the test'}
        self.trends.process_post(post)
        self.assertFalse(rpush_mock.called)
        self.assertFalse(set_post_mock.called)
        self.assertFalse(incr_mock.called)

    @patch.object(trends.Trends, 'update_person_stats')
    @patch.object(time, 'time')
    @patch.object(db.Db, 'incr')
    @patch.object(db.Db, 'set_post')
    @patch.object(db.Db, 'rpush')
    def test_process_post_names_found_1(self, rpush_mock, set_post_mock,
            incr_mock, time_mock, update_person_stats_mock):
        incr_mock.return_value = 3
        time_mock.return_value = 3600
        self.trends.persons = [
            {'name': 'name_1', 'first_name': 'first_name_1',
             'nickname': 'nickname_1', 'id': 2, 'words': ()},
            {'name': 'name_2', 'first_name': 'first_name_2',
             'nickname': 'nickname_2', 'id': 2, 'words': ()}]
        self.trends.db = db.Db()
        self.trends.stats_last_update = 0
        post = {'text': 'a name_2 worda b', 'msg': 'msg'}
        self.trends.process_post(post)
        incr_mock.assert_called_once_with('nextPostId')
        update_person_stats_mock.assert_called_once_with(
            self.trends.persons[1])
        self.assertEqual(rpush_mock.call_args_list,
            [call('person:2:posts:0', 3),
             call('posts:0', 3)])
        set_post_mock.assert_called_once_with(3,
            '{"msg": "msg", "text": "a name_2 worda b"}')

    @patch.object(trends.Trends, 'update_person_stats')
    @patch.object(time, 'time')
    @patch.object(db.Db, 'incr')
    @patch.object(db.Db, 'set_post')
    @patch.object(db.Db, 'rpush')
    def test_process_post_names_found_2(self, rpush_mock, set_post_mock,
            incr_mock, time_mock, update_person_stats_mock):
        incr_mock.return_value = 3
        time_mock.return_value = 3600
        self.trends.persons = [
            {'name': 'name_1', 'first_name': 'first_name_1',
             'nickname': 'nickname_1', 'id': 2, 'words': ()},
            {'name': 'name_2', 'first_name': 'first_name_2',
             'nickname': 'nickname_2', 'id': 3, 'words': ()}]
        self.trends.db = db.Db()
        self.trends.stats_last_update = 0
        post = {'text': 'a name_2 worda name_1 b', 'msg': 'msg'}
        self.trends.process_post(post)
        incr_mock.assert_called_once_with('nextPostId')
        self.assertEqual(update_person_stats_mock.call_args_list,
            [call(self.trends.persons[0]),
             call(self.trends.persons[1])])
        self.assertEqual(rpush_mock.call_args_list,
            [call('person:2:posts:0', 3),
             call('person:3:posts:0', 3),
             call('posts:0', 3)])
        set_post_mock.assert_called_once_with(3,
            '{"msg": "msg", "text": "a name_2 worda name_1 b"}')


if __name__ == '__main__':
    unittest.main()
