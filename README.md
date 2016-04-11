# [Halalan16.ph](http://halalan16.ph) - Twitter statistics on the 2016 Philippine Presidential elections.

**An independent study based on [Laurent Luce's 2012 research](http://www.laurentluce.com/posts/python-twitter-statistics-and-the-2012-french-presidential-election/).**

## Dependencies
- RabbitMQ
- Redis
- MySQL
- Python virtual env
- [Register your app with Twitter](https://apps.twitter.com/)

## Install Python Dependencies
```
$ virtualenv pytolab-env
(pytolab-env)$ . pytolab-env/bin/activate
(pytolab-env)$ pip install -r requirements.txt
```

## Create setup files
Under the `pytolab-trends/trends` folder, you need to make two files.

### names.txt
This file contains all the names of the of the candidates in this format:

**_ID:First\_name:Full\_name:Nick\_name:Group\_number:Words\_array_**

#### Example

```
0:Zaphod:Zaphod Beeblebrox:Zaphod:0:[]
```

### trends.cfg
This file contains all your configuration values

#### Example

```

[trends]
root = pytolab-trends/trends

[redis]
host = localhost
port = 6379

[rabbitmq]
host = localhost
userid = guest
password = guest

[twitter]
consumer_token = YOUR_TWITTER_APP_CONSUMER_TOKEN
consumer_secret = YOUR_TWITTER_APP_CONSUMER_SECRET
access_token_secret = YOUR_TWITTER_APP_ACCESS_TOKEN

[mysql]
host = localhost
user =
password =
db = trends

```

## Run tweets
`(pytolab-env)$ python tweets.py`

## Run server
`(pytolab-env)$ python server.py`

## Checkout the graphs on port 8888

http://localhost:8888