#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os
import unittest2 as unittest

from mock import patch

import trends.data as data
import trends.exceptions as exceptions

logging.basicConfig(filename='log_test_data.txt',level=logging.DEBUG)

class DataTest(unittest.TestCase):

    def setUp(self):
        pass

    def test_parse_post(self):
        post = 'author_name:<$>:1:<$>:2:<$>:body:<$>:0:<$>:{"test": 1}'\
               ':<$>:4:<$>:5'
        p = data.parse_post(post)
        self.assertDictEqual(p, {'msg': post, 'author_name': 'author_name',
            'author_id': 1, 'id': 2, 'text': 'body', 'retweeted': 0,
            'coordinates': {'test': 1}, 'time': 4, 'sentiment': 5})

    def test_parse_post_index_error(self):
        post = 'author_name:<$>:1'
        self.assertRaises(exceptions.DataError,
            data.parse_post,
            post)

    def test_parse_post_value_error(self):
        post = 'author_name:<$>:1:<$>:2:<$>:body:<$>:0:<$>:{"'\
               ':<$>:4:<$>:5'
        self.assertRaises(exceptions.DataError,
            data.parse_post,
            post)

    def test_normalize_non_unicode(self):
        s = 'été'
        self.assertEqual('ete', data.normalize(s))

    def test_normalize_unicode(self):
        s = u'été'
        self.assertEqual('ete', data.normalize(s))

    def test_get_person_words(self):
        persons = [
            {'first_name': 'first_name_1',
             'name': 'name_1',
             'nickname': 'nickname_1'},
            {'first_name': 'First namé 2',
             'name': 'name 2',
             'nickname': 'nickname 2'}]
        self.assertListEqual(data.get_persons_words(persons),
            ['first_name_1', 'name_1', 'nickname_1',
             'first', 'name', 'name', 'nickname'])

    def test_clean_post_number(self):
        post = '35'
        self.assertEqual(data.clean_post(post), ' ')

    def test_clean_post_user(self):
        post = '@test_ù'
        self.assertEqual(data.clean_post(post), ' ')

    def test_clean_post_url_1(self):
        post = 'http://example.com'
        self.assertEqual(data.clean_post(post), ' ')

    def test_clean_post_url_2(self):
        post = 'https://example.com'
        self.assertEqual(data.clean_post(post), ' ')

    def test_clean_post_url_3(self):
        post = 'https://example.com/abc'
        self.assertEqual(data.clean_post(post), ' ')

    def test_clean_post_short_url(self):
        post = 'ab.cd/ef'
        self.assertEqual(data.clean_post(post), ' ')

    def test_clean_post_punc(self):
        post = '!'
        self.assertEqual(data.clean_post(post), ' ')

    def test_clean_post(self):
        post = 'worda 35 wordb @test_ù wordc https://example.com/abc wordd'\
               ' ab.cd/ef worde ! wordf'
        self.assertEqual(data.clean_post(post),
            'worda   wordb   wordc   wordd   worde   wordf')

    def update_words_dict_get_posts_helper(self):
        posts = ['worda', 'worda', 'wordb']
        return posts

    def test_update_words_dict(self):
        posts = self.update_words_dict_get_posts_helper()
        d = {}
        freq_words = []
        persons_words = []
        self.assertDictEqual(
            data.update_words_dict(d, posts, freq_words, persons_words),
            {'worda': 2, 'wordb': 1})

    def test_update_words_dict_not_empty(self):
        posts = self.update_words_dict_get_posts_helper()
        d = {'worda': 1, 'wordc': 1}
        freq_words = []
        persons_words = []
        self.assertDictEqual(
            data.update_words_dict(d, posts, freq_words, persons_words),
            {'worda': 3, 'wordb': 1, 'wordc': 1})

    def test_update_words_dict_lower(self):
        posts = self.update_words_dict_get_posts_helper()
        posts.append('Worda')
        d = {}
        freq_words = []
        persons_words = []
        self.assertDictEqual(
            data.update_words_dict(d, posts, freq_words, persons_words),
            {'worda': 3, 'wordb': 1})

    def test_update_words_dict_short_word(self):
        posts = self.update_words_dict_get_posts_helper()
        posts.append('ab')
        d = {}
        freq_words = []
        persons_words = []
        self.assertDictEqual(
            data.update_words_dict(d, posts, freq_words, persons_words),
            {'worda': 2, 'wordb': 1})

    def test_update_words_dict_freq_words(self):
        posts = self.update_words_dict_get_posts_helper()
        d = {}
        freq_words = ['worda']
        persons_words = []
        self.assertDictEqual(
            data.update_words_dict(d, posts, freq_words, persons_words),
            {'wordb': 1})

    def test_update_words_dict_persons_words(self):
        posts = self.update_words_dict_get_posts_helper()
        d = {}
        freq_words = ['worda']
        persons_words = []
        self.assertDictEqual(
            data.update_words_dict(d, posts, freq_words, persons_words),
            {'wordb': 1})

    def test_update_words_dict_normalize(self):
        posts = self.update_words_dict_get_posts_helper()
        posts.append('wördc')
        d = {}
        freq_words = ['wordc']
        persons_words = []
        self.assertDictEqual(
            data.update_words_dict(d, posts, freq_words, persons_words),
            {'worda': 2, 'wordb': 1})

    def normalize_error(s):
        if s == 'wordc':
            raise UnicodeDecodeError(
                'ascii', '\xff', 0, 1, 'ordinal not in range''a')
        else:
            return s

    @patch.object(data, 'normalize', normalize_error)
    def test_update_words_dict_normalize_error(self):
        posts = self.update_words_dict_get_posts_helper()
        posts.append('wordc')
        d = {}
        freq_words = []
        persons_words = []
        self.assertDictEqual(
            data.update_words_dict(d, posts, freq_words, persons_words),
            {'worda': 2, 'wordb': 1})

    def test_get_freq_words(self):
        words = data.get_freq_words('freq_words.txt')
        self.assertListEqual(words, ['word1', 'word2', 'word3'])

    def test_get_text_language_en(self):
        self.assertEqual(data.get_text_language('je suis at la maison'), 'en')

    def test_get_text_language_fr(self):
        self.assertEqual(data.get_text_language('je suis à la maison'), '')

    def test_find_text_person_words_o_minus_1_not_found(self):
        name = 'name'
        words = (('worda', -1), ('wordb', -1))
        text = 'wordc name'
        self.assertEqual(data.find_text_person_words(text, name, words), -1)

    def test_find_text_person_words_o_minus_1_found(self):
        name = 'name'
        words = (('worda', -1), ('wordb', -1))
        text = 'wordb namex'
        self.assertEqual(data.find_text_person_words(text, name, words), 10)

    def test_find_text_person_words_o_minus_2_not_found(self):
        name = 'name'
        words = (('worda', -2), ('wordb', -2))
        text = 'wordcname'
        self.assertEqual(data.find_text_person_words(text, name, words), -1)

    def test_find_text_person_words_o_minus_2_found(self):
        name = 'name'
        words = (('worda', -2), ('wordb', -2))
        text = 'wordaname'
        self.assertEqual(data.find_text_person_words(text, name, words), 9)

    def test_find_text_person_words_o_1_not_found(self):
        name = 'name'
        words = (('worda', 1), ('wordb', 1))
        text = 'name wordc'
        self.assertEqual(data.find_text_person_words(text, name, words), -1)

    def test_find_text_person_words_o_1_found(self):
        name = 'name'
        words = (('worda', 1), ('wordb', 1))
        text = 'name worda'
        self.assertEqual(data.find_text_person_words(text, name, words), 10)

    def test_find_text_person_words_o_2_not_found(self):
        name = 'name'
        words = (('worda', 2), ('wordb', 2))
        text = 'namewordc'
        self.assertEqual(data.find_text_person_words(text, name, words), -1)

    def test_find_text_person_words_o_2_found(self):
        name = 'name'
        words = (('worda', 2), ('wordb', 2))
        text = 'nameworda'
        self.assertEqual(data.find_text_person_words(text, name, words), 9)

    def test_check_names_not_found(self):
        names = ('name_a', 'name_b')
        text = 'name_c name_d'
        words = (('worda', 1), ('wordb', 1))
        self.assertEqual(data.check_names(names, text, words), 0)

    def test_check_names_found_without_non_allowed_words(self):
        names = ('name_a', 'name_b')
        text = 'name_c name_a'
        words = (('worda', 1), ('wordb', 1))
        self.assertEqual(data.check_names(names, text, words), 1)

    def test_check_names_found_with_non_allowed_words(self):
        names = ('name_a', 'name_b')
        text = 'name_c name_a worda'
        words = (('worda', 1), ('wordb', 1))
        self.assertEqual(data.check_names(names, text, words), 2)

    def test_check_names_found_without_non_allowed_words_second(self):
        names = ('name_a', 'name_b')
        text = 'name_c name_a worda name_b'
        words = (('worda', 1), ('wordb', 1))
        self.assertEqual(data.check_names(names, text, words), 1)

    def test_get_names_person_name(self):
        person = {'name': 'test_name', 'nickname': ''}
        expected = ['test_name']
        self.assertListEqual(data.get_names(person), expected)

    def test_get_names_person_name_with_space(self):
        person = {'name': 'test name', 'nickname': ''}
        expected = ['test name', 'test-name']
        self.assertListEqual(data.get_names(person), expected)

    def test_get_names_person_name_nickname(self):
        person = {'name': 'test_name', 'nickname': 'test_nickname'}
        expected = ['test_name', 'test_nickname']
        self.assertListEqual(data.get_names(person), expected)


if __name__ == '__main__':
    unittest.main()
