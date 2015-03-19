# coding:utf-8

import sys
import os
import shutil
import getopt
import requests
import json
import webbrowser
import random
from termcolor import colored
from spider import YoudaoSpider
from model import Word
import config


def show_result(result):
    """
    展示查询结果
    :param result: 与有道API返回的json 数据结构一致的dict
    """
    if result['errorCode'] != 0:
        print colored(YoudaoSpider.error_code[result['errorCode']], 'red')
    else:
        print colored('[%s]' % result['query'], 'magenta')
        if 'basic' in result:
            if 'us-phonetic' in result['basic']:
                print colored(u'美音:', 'blue'), colored('[%s]' % result['basic']['us-phonetic'], 'green'),
            if 'uk-phonetic' in result['basic']:
                print colored(u'英音:', 'blue'), colored('[%s]' % result['basic']['uk-phonetic'], 'green')
            if 'phonetic' in result['basic']:
                print colored(u'拼音:', 'blue'), colored('[%s]' % result['basic']['phonetic'], 'green')

            print colored(u'基本词典:', 'blue')
            print colored('\t'+'\n\t'.join(result['basic']['explains']), 'yellow')

        if 'translation' in result:
            print colored(u'有道翻译:', 'blue')
            print colored('\t'+'\n\t'.join(result['translation']), 'cyan')

        if 'web' in result:
            print colored(u'网络释义:', 'blue')
            for item in result['web']:
                print '\t' + colored(item['key'], 'cyan') + ': ' + '; '.join(item['value'])


def play(voice_file):
    out1 = os.dup(1)
    out2 = os.dup(2)
    os.close(1)
    os.close(2)
    try:
        webbrowser.open(voice_file)
    finally:
        os.dup2(out1, 1)
        os.dup2(out2, 2)


def query(keyword, use_db=True, use_api=False, play_voice=False):
    word = Word.get_word(keyword)
    if use_db and word:
        show_result(json.loads(word.json_data))
    else:
        if not word:
            word = Word()
        spider = YoudaoSpider(keyword)
        try:
            result = spider.get_result(use_api)
        except requests.HTTPError, e:
            print colored(u'网络错误: %s' % e.message, 'red')
            sys.exit()
        else:
            show_result(result)
            word.keyword = keyword
            word.json_data = json.dumps(result)
            word.save()

    if play_voice:
        print(colored(u'获取发音:{word}'.format(word=keyword), 'green'))
        voice_file = YoudaoSpider.get_voice(keyword)
        print(colored(u'获取成功,播放中...', 'green'))
        play(voice_file)


def show_db_list():
    print colored(u'保存在数据库中的单词及查询次数:', 'blue')
    for word in Word.select():
        print colored(word.keyword, 'cyan'), colored(str(word.count), 'green')


def del_word(keyword):
    if keyword:
        try:
            word = Word.select().where(Word.keyword == keyword).get()
            word.delete_instance()
            print(colored(u'已删除{0}'.format(keyword), 'blue'))
        except Word.DoesNotExist:
            print(colored(u'没有找到{0}'.format(keyword), 'red'))
        config.silent_remove(os.path.join(config.VOICE_DIR, keyword+'.mp3'))
    else:
        count = Word.delete().execute()
        shutil.rmtree(config.VOICE_DIR, ignore_errors=True)
        print(colored(u'共删除{0}个单词'.format(count), 'blue'))


def show_help():
    print(u"""
    控制台下的有道词典 版本{ver}
    新增对StarDict 的支持，默认优先使用StarDict
    默认通过解析有道网页版获取查询结果, 没有词典结果时自动使用有道翻译,
    查询结果会保存到sqlite 数据库中
    使用方法 yd word [-a] [-n] [-l] [-c] [-v] [-d word] [-y] [-s path] [--help]
    [-a] 使用API 而不是解析网页获取结果
    [-n] 强制重新获取, 不管数据库中是否已经保存
    [-l] 列出数据库中保存的所有单词
    [-c] 清空数据库
    [-v] 获取单词发音, 单独使用 yd -v 可以获取上一个查询单词的发音
    [-d word] 删除数据库中某个单词
    [-y] 优先使用stardict词典
    [-s path] 设置stardict词典路径
    [--help] 显示帮助信息
    """.format(ver=config.VERSION))


def main():
    config.prepare()
    try:
        options, args = getopt.getopt(sys.argv[1:], 'anld:cvs:y', ['help'])
    except getopt.GetoptError:
        options = [('--help', '')]
    if ('--help', '') in options:
        show_help()
        return

    use_api = False
    use_db = True
    play_voice = False
    use_dict = True
    for opt in options:
        if opt[0] == '-a':
            use_api = True
        elif opt[0] == '-n':
            use_db = False
        elif opt[0] == '-l':
            show_db_list()
            sys.exit()
        elif opt[0] == '-d':
            del_word(opt[1])
            sys.exit()
        elif opt[0] == '-c':
            del_word(None)
            sys.exit()
        elif opt[0] == '-v':
            play_voice = True
        elif opt[0] == '-s':
            print u'stardict 路径设置成功：', opt[1]
            config.set_dict_path(opt[1])
            sys.exit()
        elif opt[0] == '-y':
            use_dict = False

    keyword = unicode(' '.join(args), encoding=sys.getfilesystemencoding())

    # 播放上一个单词的声音
    if play_voice and not keyword:
        word = Word.get_last_word()
        keyword = word.keyword
        query(keyword, play_voice=True, use_db=True)
    else:
        while not keyword:
            keyword = raw_input(colored('input a word: ', 'blue'))

        # 查询词典
        stardict_match = False
        if use_dict and config.config.get('stardict'):
            colors = ['yellow', 'blue', 'cyan']
            from lib.cpystardict import Dictionary
            stardict_base = config.config.get('stardict')
            for dic_dir in os.listdir(stardict_base):
                dic_file = os.listdir(os.path.join(stardict_base, dic_dir))[0]
                name, ext = os.path.splitext(dic_file)
                name = name.split('.')[0]
                dic = Dictionary(os.path.join(stardict_base, dic_dir, name))
                dic_exp = dic[keyword]
                if dic_exp:
                    print colored(u"[{dic}]:{word}".format(dic=name, word=keyword), 'green')
                    color = colors[random.randint(0, len(colors)-1)]
                    print colored(dic_exp, color)
                    print colored('========================', 'magenta')
                    stardict_match = True

        if not stardict_match:
            query(keyword, use_db, use_api, play_voice)

if __name__ == '__main__':
    main()