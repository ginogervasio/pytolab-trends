#!/usr/bin/python
# -*- coding: utf-8 -*-

import datetime
import json
import logging
import re
import time
import unicodedata

import exceptions

def parse_post(data):
    """
    Parse post string containing attributes values.
    
    Attributes values are separated by :<$>:.
    """
    try:
        post = {}
        s = data.split(':<$>:')
        post['msg'] = data
        post['author_name'] = s[0]
        post['author_id'] = int(s[1])
        post['id'] = int(s[2])
        post['text'] = s[3]
        post['retweeted'] = int(s[4])
        post['coordinates'] = json.loads(s[5])
        post['time'] = int(s[6])
        post['sentiment'] = int(s[7])
        return post
    except (IndexError, ValueError):
        raise exceptions.DataError()

def normalize(s):
    """
    Strip accents from chars: é -> e
    """
    if isinstance( s, str ):
        s = unicode(s, 'utf-8')
    return ''.join(
        (c for c in unicodedata.normalize('NFD', s) 
            if unicodedata.category(c) != 'Mn'))

def get_persons_words(persons):
    """
    Returns possible names for a list of persons.

    Add a list containing: first name, last name and nickname, for
    each person.
    """
    words = []
    for person in persons:
        fn = normalize(person['first_name']).lower().split()
        n = normalize(person['name']).lower().split()
        ni = normalize(person['nickname']).lower().split()
        for e in [fn, n, ni]:
            words.extend(e)
    return [w for w in words if len(w) > 2]

def clean_post(post):
    """
    Remove numbers, author names, urls and punctuation.
    """ 
    number_re = re.compile(r'[0-9]+')
    user_re = re.compile(r'@([A-Za-z0-9_ùûüÿàâæçéèêëïîôœ]+)')
    url_re = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|'\
        '(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    short_url_re = re.compile(r'[a-zA-Z]+\.[a-zA-Z]+/[a-zA-Z0-9]+')
    punc_re = re.compile(r'[!"#$%&\'()*+,-./:;<=>?\[\\\]^_`{|}~’»«]')
    p = post
    for r in [number_re, user_re, url_re, short_url_re, punc_re]:
        p = re.sub(r, ' ', p)
    return p

def update_words_dict(words_dict, posts, freq_words, persons_words):
    """
    Update words_dict with words contained in posts.

    Do not include words part of freq_words and person_words.
    """
    strs = []
    for post in posts:
        p = clean_post(post)
        strs.append(p)
    s = ' '.join(strs)
    words = s.split()
    words = (w for w in words if len(w) > 2)
    for w in words:
        wl = w.lower()
        if wl in words_dict:
            words_dict[wl] += 1
        else:
            try:
                wls = normalize(wl)
                if ((wls not in freq_words)
                        and (wls not in persons_words)):
                    words_dict[wl] = 1
            except UnicodeDecodeError, e:
                logging.warning('Cannot process %s', wl)
    return words_dict

def get_freq_words(path):
    """
    Read most frequent words from file located at path.
    """
    with open(path, 'r') as f:
       return [l.rstrip('\n') for l in f]
      
def get_text_language(text):
    """
    Return text language.

    Check for common english words. Return 'en' if any. Return 'fr' otherwise.
    """ 
    ew = (' at ', ' the ', ' are ', ' to ', ' he ', ' she ', ' in ',
         ' is ')
    if any(n in text for n in ew):
        return 'en'
    else:
        return 'fr'

def find_text_person_words(text, name, words):
    """Check if one of the words preceeds or follows a name.

    If o == -1: check for ' word name', 'word-name'... 
    If o == -2: check for ' wordname', ' -wordname'... 
    If o == 1: check for 'name word', 'nameword', 'name--word'...
    If o == 2: check for 'nameword', 'nameword ',...
    """
    if words:
        for w, o in words:
            if o == -1:
                pattern = '(^| |\.|\"|\'|\-|#|@)%s[ \-#@\.]*%s' % (
                    w.lower(), name)
            elif o == -2:
                pattern = '(^| |\.|\"|\'|\-|#|@)%s%s' % (w.lower(), name)
            elif o == 1:
                pattern = '%s[ \-#@\.]*%s($| |\.|\"|\'|\-)' % (name, w.lower())
            elif o == 2:
                pattern = '%s%s($| |\.|\"|\'|\-)' % (name, w.lower())
            m = re.search(pattern, text)
            if m:
                return m.end()
    return -1

def check_names(names, text, words):
    """Check if person is referred in the text

    Returns 0 if name not found
    Returns 1 if name found without non-allowed words
    Returns 2 if name found with non-allowed words
    """ 
    res = 0
    for n in names:
        idx = text.find(n)
        g_end = 0
        while idx != -1:
            g_end = find_text_person_words(text[g_end:], n, words)
            if g_end == -1:
                return 1
            else:
                res = 2
            idx = text.find(n, idx+1)
    return res

def get_names(person):
    """
    Returns list containing a person's name, nickname. 
    """
    name = normalize(person['name']).lower()
    names = [name,]
    if ' ' in name:
        names.append('-'.join(name.split(' ')))
    if person['nickname']:
        names.append(normalize(person['nickname']).lower())

    return names

def get_fr_datetime_from_timestamp(ts):
    wt = datetime.datetime(2011, 10, 30, 1, 0, 0, 0)
    st = datetime.datetime(2012, 3, 25, 2, 0, 0, 0)
    d = datetime.datetime.utcfromtimestamp(ts)
    if d < wt or d > st:
        # timestamp before start of winter time 2011 or after start
        # of summer time 2012
        d = datetime.datetime.fromtimestamp(ts + 7200)
    else:
        d = datetime.datetime.fromtimestamp(ts + 3600)

    return d
   
def get_str_from_timestamp(ts, short=False):
    d = get_fr_datetime_from_timestamp(ts)
    if short:
        s = d.strftime('%m-%d')
    else:
        s = d.strftime('%Y-%m-%d %H:%M:%S')
    return s

