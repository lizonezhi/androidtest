#!/usr/bin/env python
# coding=utf-8

__author__ = "lzz"
'''
参考：
https://github.com/openatx/uiautomator2#uiautomator2
https://github.com/gb112211/Adb-For-Test
支持python3.6
目前功能无需在手机上装任何程序
'''
import tempfile
import os
import sys
import platform
import subprocess
import re
import time
from time import sleep

from androidtest import adbutils
from retry import retry
import six.moves.urllib.parse as urlparse
from functools import partial
import functools
import progress.bar
from subprocess import list2cmdline
import logging
import six
HTTP_TIMEOUT = 60
import hashlib
import json

import xml.etree.cElementTree as ET

PATH = lambda p: os.path.abspath(p)

# 判断系统类型，windows使用findstr，linux使用grep
system = platform.system()
if system is "Windows":
    find_util = "findstr"
else:
    find_util = "grep"

# # 判断是否设置环境变量ANDROID_HOME
# if "ANDROID_HOME" in os.environ:
#     if system == "Windows":
#         command = os.path.join(os.environ["ANDROID_HOME"], "platform-tools", "adb.exe")
#     else:
#         command = os.path.join(os.environ["ANDROID_HOME"], "platform-tools", "adb")
# else:
#     raise EnvironmentError(
#         "Adb not found in $ANDROID_HOME path: %s." % os.environ["ANDROID_HOME"])
command = 'adb'
class UiaError(Exception):
    pass
class GatewayError(UiaError):
    def __init__(self, response, description):
        self.response = response
        self.description = description

    def __str__(self):
        return "uiautomator2.GatewayError(" + self.description + ")"
class JsonRpcError(UiaError):
    @staticmethod
    def format_errcode(errcode):
        m = {
            -32700: 'Parse error',
            -32600: 'Invalid Request',
            -32601: 'Method not found',
            -32602: 'Invalid params',
            -32603: 'Internal error',
            -32001: 'Jsonrpc error',
            -32002: 'Client error',
        }
        if errcode in m:
            return m[errcode]
        if errcode >= -32099 and errcode <= -32000:
            return 'Server error'
        return 'Unknown error'

    def __init__(self, error={}, method=None):
        self.code = error.get('code')
        self.message = error.get('message', '')
        self.data = error.get('data', '')
        self.method = method

    def __str__(self):
        return '%d %s: <%s> data: %s, method: %s' % (
            self.code, self.format_errcode(self.code), self.message, self.data,
            self.method)

    def __repr__(self):
        return repr(str(self))
class SessionBrokenError(UiaError):
    pass


class UiObjectNotFoundError(JsonRpcError):
    pass


class UiAutomationNotConnectedError(JsonRpcError):
    pass


class NullObjectExceptionError(JsonRpcError):
    pass


class NullPointerExceptionError(JsonRpcError):
    pass


class StaleObjectExceptionError(JsonRpcError):
    pass


class _ProgressBar(progress.bar.Bar):
    message = "progress"
    suffix = '%(percent)d%% [%(eta_td)s, %(speed)s]'

    @property
    def speed(self):
        return humanize.naturalsize(
            self.elapsed and self.index / self.elapsed, gnu=True) + '/s'


def log_print(s):
    thread_name = threading.current_thread().getName()
    print(thread_name + ": " + datetime.now().strftime('%H:%M:%S,%f')[:-3] +
          " " + s)


def intersect(rect1, rect2):
    top = rect1["top"] if rect1["top"] > rect2["top"] else rect2["top"]
    bottom = rect1["bottom"] if rect1["bottom"] < rect2["bottom"] else rect2[
        "bottom"]
    left = rect1["left"] if rect1["left"] > rect2["left"] else rect2["left"]
    right = rect1["right"] if rect1["right"] < rect2["right"] else rect2[
        "right"]
    return left, top, right, bottom

def U(x):
    if six.PY3:
        return x
    return x.decode('utf-8') if type(x) is str else x

# 判断是否为数字
def is_number(s):
    '''
    判断是否由数字组成，包括小数
    '''
    try:
        float(s)
        return True
    except ValueError:
        pass
    try:
        import unicodedata
        unicodedata.numeric(s)
        return True
    except (TypeError, ValueError):
        pass
    return False

class ImageUtils(object):
    '''
    目前只能比较相似度返回True，暂时不用
    '''
    def __init__(self, device_id=""):
        """
        初始化，获取系统临时文件存放目录
        """
        self.utils = Device(device_id)
        self.tempFile = tempfile.gettempdir()
        print(tempfile.gettempdir())
    def screenShot(self):
        """
        截取设备屏幕
        """
        self.utils.shell("screencap -p /data/local/tmp/temp.png").wait()
        self.utils.adb("pull /data/local/tmp/temp.png %s" %self.tempFile).wait()

        return self

    def writeToFile(self, dirPath, imageName, form = "png"):
        """
        将截屏文件写到本地
        usage: screenShot().writeToFile("d:\\screen", "image")
        """
        if not os.path.isdir(dirPath):
            os.makedirs(dirPath)
        shutil.copyfile(PATH("%s/temp.png" %self.tempFile), PATH("%s/%s.%s" %(dirPath, imageName, form)))
        self.utils.shell("rm /data/local/tmp/temp.png")

    def loadImage(self, imageName):
        """
        加载本地图片
        usage: lodImage("d:\\screen\\image.png")
        """
        if os.path.isfile(imageName):
            load = Image.open(imageName)
            return load
        else:
            print("image is not exist")

    def subImage(self, box):
        """
        截取指定像素区域的图片
        usage: box = (100, 100, 600, 600)
              screenShot().subImage(box)
        """
        image = Image.open(PATH("%s/temp.png" %self.tempFile))
        newImage = image.crop(box)
        newImage.save(PATH("%s/temp.png" %self.tempFile))

        return self

    #http://testerhome.com/topics/202
    def sameAs(self,loadImage):
        """
        比较两张截图的相似度，完全相似返回True
        usage： load = loadImage("d:\\screen\\image.png")
                screen().subImage(100, 100, 400, 400).sameAs(load)
        """
        import math
        import operator

        image1 = Image.open(PATH("%s/temp.png" %self.tempFile))
        image2 = loadImage


        histogram1 = image1.histogram()
        histogram2 = image2.histogram()

        differ = math.sqrt(reduce(operator.add, list(map(lambda a,b: (a-b)**2, \
                                                         histogram1, histogram2)))/len(histogram1))
        if differ == 0:
            return True
        else:
            return False

class Element(object):
    """
    通过元素定位
    """

    def __init__(self, device_id=""):
        """
        初始化，获取系统临时文件存储目录，定义匹配数字模式
        """
        self.utils = Device(device_id)
        self.tempFile = tempfile.gettempdir()
        self.pattern = re.compile(r"\d+")

    def __uidump(self):
        """
        获取当前Activity的控件树
        """
        if int(self.utils.getSdkVersion()) >= 19:
            self.utils.shell("uiautomator dump --compressed /data/local/tmp/uidump.xml").wait()
        else:
            self.utils.shell("uiautomator dump /data/local/tmp/uidump.xml").wait()
        self.utils.adb("pull data/local/tmp/uidump.xml %s" % self.tempFile).wait()
        # self.utils.shell("rm /data/local/tmp/uidump.xml").wait()

    def __element(self, attrib, name):
        """
        同属性单个元素，返回单个坐标元组，(x, y)
        :args:
        - attrib - node节点中某个属性
        - name - node节点中某个属性对应的值
        """
        Xpoint = None
        Ypoint = None

        self.__uidump()
        tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
        treeIter = tree.iter(tag="node")
        for elem in treeIter:
            if elem.attrib[attrib] == name:
                # 获取元素所占区域坐标[x, y][x, y]
                bounds = elem.attrib["bounds"]

                # 通过正则获取坐标列表
                coord = self.pattern.findall(bounds)

                # 求取元素区域中心点坐标
                Xpoint = (int(coord[2]) - int(coord[0])) / 2.0 + int(coord[0])
                Ypoint = (int(coord[3]) - int(coord[1])) / 2.0 + int(coord[1])
                break

        if Xpoint is None or Ypoint is None:
            raise Exception("Not found this element(%s) in current activity" % name)

        return (Xpoint, Ypoint)

    def d(self,attrib=None,name=None, **msg):
        """
        同属性单个元素，返回单个坐标元组，(x, y)
        :args:
        - attrib - node节点中某个属性
        - name - node节点中某个属性对应的值
        用法：d(resourceId='com.android.calculator2:id/op_mul')
             d(text='8')
             d(content_desc='乘')
        """
        if attrib and name:
            attrib = attrib.replace('resourceId', 'resource-id').replace('description', 'content-desc')
        else:
            for attrib in msg:
                try:
                    if msg['resourceId'] != '':
                        attrib = 'resource-id'
                        name = msg['resourceId']
                        break
                except:
                    pass
                try:
                    if msg['text'] != '':
                        attrib = 'text'
                        name = msg['text']
                        break
                except:
                    pass
                try:
                    if msg['content_desc'] != '':
                        attrib = 'content-desc'
                        name = msg['content_desc']
                        break
                except:
                    pass
        Xpoint = None
        Ypoint = None

        self.__uidump()
        tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
        treeIter = tree.iter(tag="node")
        for elem in treeIter:
            if elem.attrib[attrib] == name:
                # 获取元素所占区域坐标[x, y][x, y]
                bounds = elem.attrib["bounds"]

                # 通过正则获取坐标列表
                coord = self.pattern.findall(bounds)

                # 求取元素区域中心点坐标
                Xpoint = (int(coord[2]) - int(coord[0])) / 2.0 + int(coord[0])
                Ypoint = (int(coord[3]) - int(coord[1])) / 2.0 + int(coord[1])
                break

        if Xpoint is None or Ypoint is None:
            raise Exception("Not found this element(%s) in current activity" % name)
        return (Xpoint, Ypoint)
    def d_right_corner(self,attrib=None,name=None, **msg):
        """
        同属性单个元素，返回单个 右下角 坐标元组，(x, y)
        :args:
        - attrib - node节点中某个属性
        - name - node节点中某个属性对应的值
        用法：d(resourceId='com.android.calculator2:id/op_mul')
             d(text='8')
             d(content_desc='乘')
        """
        if attrib and name:
            attrib = attrib.replace('resourceId', 'resource-id').replace('description', 'content-desc')
        else:
            for attrib in msg:
                try:
                    if msg['resourceId'] != '':
                        attrib = 'resource-id'
                        name = msg['resourceId']
                        break
                except:
                    pass
                try:
                    if msg['text'] != '':
                        attrib = 'text'
                        name = msg['text']
                        break
                except:
                    pass
                try:
                    if msg['content_desc'] != '':
                        attrib = 'content-desc'
                        name = msg['content_desc']
                        break
                except:
                    pass
        Xpoint = None
        Ypoint = None

        self.__uidump()
        tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
        treeIter = tree.iter(tag="node")
        for elem in treeIter:
            if elem.attrib[attrib] == name:
                # 获取元素所占区域坐标[x, y][x, y]
                bounds = elem.attrib["bounds"]

                # 通过正则获取坐标列表
                coord = self.pattern.findall(bounds)

                # 求取元素区域右下角点坐标
                Xpoint = (int(coord[2]) - int(coord[0])) * 0.99 + int(coord[0])
                Ypoint = (int(coord[3]) - int(coord[1])) * 0.99 + int(coord[1])
                break

        if Xpoint is None or Ypoint is None:
            raise Exception("Not found this element(%s) in current activity" % name)
        return (Xpoint, Ypoint)

    def info(self,attrib=None,name=None, **msg):
        """
        同属性单个元素，返回单个控件所有属性
        :args:
        - attrib - node节点中某个属性
        - name - node节点中某个属性对应的值
        用法：d(resourceId='com.android.calculator2:id/op_mul')
             d(text='8')
             d(content_desc='乘')
        返回参数：{'index': '14', 'text': '×', 'resource-id': 'com.android.calculator2:id/op_mul', 'class': 'android.widget.Button', 'package': 'com.android.calculator2', 'content-desc': '乘', 'checkable': 'false', 'checked': 'false', 'clickable': 'true', 'enabled': 'true', 'focusable': 'true', 'focused': 'false', 'scrollable': 'false', 'long-clickable': 'false', 'password': 'false', 'selected': 'false', 'bounds': '[370,556][426,622]'}
        """
        if attrib and name:
            attrib = attrib.replace('resourceId', 'resource-id').replace('description', 'content-desc')
        else:
            for attrib in msg:
                try:
                    if msg['resourceId'] != '':
                        attrib = 'resource-id'
                        name = msg['resourceId']
                        break
                except:
                    pass
                try:
                    if msg['text'] != '':
                        attrib = 'text'
                        name = msg['text']
                        break
                except:
                    pass
                try:
                    if msg['content_desc'] != '':
                        attrib = 'content-desc'
                        name = msg['content_desc']
                        break
                except:
                    pass

        element_info = None
        self.__uidump()
        tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
        treeIter = tree.iter(tag="node")
        for elem in treeIter:
            if elem.attrib[attrib] == name:
                element_info = elem.attrib
                break
        return element_info
    # def infomation(self, msg):
    #     """
    #     同属性单个元素，返回单个控件所有属性
    #     :args:
    #     - attrib - node节点中某个属性
    #     - name - node节点中某个属性对应的值
    #     用法：d(('resourceId,'com.android.calculator2:id/op_mul'))
    #     返回参数：{'index': '14', 'text': '×', 'resource-id': 'com.android.calculator2:id/op_mul', 'class': 'android.widget.Button', 'package': 'com.android.calculator2', 'content-desc': '乘', 'checkable': 'false', 'checked': 'false', 'clickable': 'true', 'enabled': 'true', 'focusable': 'true', 'focused': 'false', 'scrollable': 'false', 'long-clickable': 'false', 'password': 'false', 'selected': 'false', 'bounds': '[370,556][426,622]'}
    #     """
    #     attrib = msg[0].replace('resourceId','resource-id').replace('description','content-desc')
    #     name = msg[1]
    #     element_info = None
    #     self.__uidump()
    #     tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
    #     treeIter = tree.iter(tag="node")
    #     for elem in treeIter:
    #         if elem.attrib[attrib] == name:
    #             element_info = elem.attrib
    #             break
    #     return element_info
    def exists(self,attrib=None,name=None, **msg):
        """
        同属性单个元素，返回boolean
        :args:
        - attrib - node节点中某个属性
        - name - node节点中某个属性对应的值
        用法：d(('resourceId,'com.android.calculator2:id/op_mul'))
        返回参数：{'index': '14', 'text': '×', 'resource-id': 'com.android.calculator2:id/op_mul', 'class': 'android.widget.Button', 'package': 'com.android.calculator2', 'content-desc': '乘', 'checkable': 'false', 'checked': 'false', 'clickable': 'true', 'enabled': 'true', 'focusable': 'true', 'focused': 'false', 'scrollable': 'false', 'long-clickable': 'false', 'password': 'false', 'selected': 'false', 'bounds': '[370,556][426,622]'}
        """
        if attrib and name:
            attrib = attrib.replace('resourceId', 'resource-id').replace('description', 'content-desc')
        else:
            for attrib in msg:
                try:
                    if msg['resourceId'] != '':
                        attrib = 'resource-id'
                        name = msg['resourceId']
                        break
                except:
                    pass
                try:
                    if msg['text'] != '':
                        attrib = 'text'
                        name = msg['text']
                        break
                except:
                    pass
                try:
                    if msg['content_desc'] != '':
                        attrib = 'content-desc'
                        name = msg['content_desc']
                        break
                except:
                    pass
        element_info = None
        self.__uidump()
        tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
        treeIter = tree.iter(tag="node")
        for elem in treeIter:
            if elem.attrib[attrib] == name:
                element_info = elem.attrib
                break
        return True if element_info else False

    def __elements(self, attrib, name):
        """
        同属性多个元素，返回坐标元组列表，[(x1, y1), (x2, y2)]
        """
        pointList = []
        self.__uidump()
        tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
        treeIter = tree.iter(tag="node")
        for elem in treeIter:
            if elem.attrib[attrib] == name:
                bounds = elem.attrib["bounds"]
                coord = self.pattern.findall(bounds)
                Xpoint = (int(coord[2]) - int(coord[0])) / 2.0 + int(coord[0])
                Ypoint = (int(coord[3]) - int(coord[1])) / 2.0 + int(coord[1])

                # 将匹配的元素区域的中心点添加进pointList中
                pointList.append((Xpoint, Ypoint))

        return pointList

    def __bound(self, attrib, name):
        """
        同属性单个元素，返回单个坐标区域元组,(x1, y1, x2, y2)
        """
        coord = []

        self.__uidump()
        tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
        treeIter = tree.iter(tag="node")
        for elem in treeIter:
            if elem.attrib[attrib] == name:
                bounds = elem.attrib["bounds"]
                coord = self.pattern.findall(bounds)

        if not coord:
            raise Exception("Not found this element(%s) in current activity" % name)

        return (int(coord[0]), int(coord[1]), int(coord[2]), int(coord[3]))

    def __bounds(self, attrib, name):
        """
        同属性多个元素，返回坐标区域列表，[(x1, y1, x2, y2), (x3, y3, x4, y4)]
        """

        pointList = []
        self.__uidump()
        tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
        treeIter = tree.iter(tag="node")
        for elem in treeIter:
            if elem.attrib[attrib] == name:
                bounds = elem.attrib["bounds"]
                coord = self.pattern.findall(bounds)
                pointList.append((int(coord[0]), int(coord[1]), int(coord[2]), int(coord[3])))

        return pointList

    def __checked(self, attrib, name):
        """
        返回布尔值列表
        """
        boolList = []
        self.__uidump()
        tree = ET.ElementTree(file=PATH("%s/uidump.xml" % self.tempFile))
        treeIter = tree.iter(tag="node")
        for elem in treeIter:
            if elem.attrib[attrib] == name:
                checked = elem.attrib["checked"]
                if checked == "true":
                    boolList.append(True)
                else:
                    boolList.append(False)

        return boolList

    def findElementByName(self, name):
        """
        通过元素名称定位单个元素
        usage: findElementByName(u"设置")
        """
        return self.__element("text", name)

    def findElementsByName(self, name):
        """
        通过元素名称定位多个相同text的元素
        """
        return self.__elements("text", name)

    def findElementByClass(self, className):
        """
        通过元素类名定位单个元素
        usage: findElementByClass("android.widget.TextView")
        """
        return self.__element("class", className)

    def findElementsByClass(self, className):
        """
        通过元素类名定位多个相同class的元素
        """
        return self.__elements("class", className)

    def findElementById(self, id):
        """
        通过元素的resource-id定位单个元素
        usage: findElementsById("com.android.deskclock:id/imageview")
        """
        return self.__element("resource-id", id)

    def findElementsById(self, id):
        """
        通过元素的resource-id定位多个相同id的元素
        """
        return self.__elements("resource-id", id)

    def findElementByContentDesc(self, contentDesc):
        """
        通过元素的content-desc定位单个元素
        """
        return self.__element("content-desc", contentDesc)

    def findElementsByContentDesc(self, contentDesc):
        """
        通过元素的content-desc定位多个相同的元素
        """
        return self.__elements("content-desc", contentDesc)

    def getElementBoundByName(self, name):
        """
        通过元素名称获取单个元素的区域
        """
        return self.__bound("text", name)

    def getElementBoundsByName(self, name):
        """
        通过元素名称获取多个相同text元素的区域
        """
        return self.__bounds("text", name)

    def getElementBoundByClass(self, className):
        """
        通过元素类名获取单个元素的区域
        """
        return self.__bound("class", className)

    def getElementBoundsByClass(self, className):
        """
        通过元素类名获取多个相同class元素的区域
        """
        return self.__bounds("class", className)

    def getElementBoundByContentDesc(self, contentDesc):
        """
        通过元素content-desc获取单个元素的区域
        """
        return self.__bound("content-desc", contentDesc)

    def getElementBoundsByContentDesc(self, contentDesc):
        """
        通过元素content-desc获取多个相同元素的区域
        """
        return self.__bounds("content-desc", contentDesc)

    def getElementBoundById(self, id):
        """
        通过元素id获取单个元素的区域
        """
        return self.__bound("resource-id", id)

    def getElementBoundsById(self, id):
        """
        通过元素id获取多个相同resource-id元素的区域
        """
        return self.__bounds("resource-id", id)

    def isElementsCheckedByName(self, name):
        """
        通过元素名称判断checked的布尔值，返回布尔值列表
        """
        return self.__checked("text", name)

    def isElementsCheckedById(self, id):
        """
        通过元素id判断checked的布尔值，返回布尔值列表
        """
        return self.__checked("resource-id", id)

    def isElementsCheckedByClass(self, className):
        """
        通过元素类名判断checked的布尔值，返回布尔值列表
        """
        return self.__checked("class", className)
class Keycode():
    HOME键 = 3
    返回键 = 4
    打开拨号应用 = 5
    挂断电话 = 6
    增加音量 = 24
    降低音量 = 25
    电源键 = 26
    拍照需要在相机应用里 = 27
    换行 = 61
    KEYCODE_TAB = 61
    打开浏览器 = 64
    回车 = 66
    # 回车 = KEYCODE_ENTER
    退格键 = 67
    KEYCODE_DEL = 67
    菜单键 = 82
    通知键 = 83
    播放暂停 = 85
    停止播放 = 86
    播放下一首 = 87
    播放上一首 = 88
    移动光标到行首或列表顶部 = 122
    移动光标到行末或列表底部 = 123
    恢复播放 = 126
    暂停播放 = 127
    扬声器静音键 = 164
    打开系统设置 = 176
    切换应用 = 187
    打开联系人 = 207
    打开日历 = 208
    打开音乐 = 209
    打开计算器 = 210
    降低屏幕亮度 = 220
    提高屏幕亮度 = 221
    系统休眠 = 223
    点亮屏幕 = 224
    打开语音助手 = 231
    如果没有wakelock则让系统休眠 = 276

    POWER = 26
    BACK = 4
    HOME = 3
    MENU = 82
    VOLUME_UP = 24
    VOLUME_DOWN = 25
    SPACE = 62
    BACKSPACE = 67
    ENTER = 66
    MOVE_HOME = 122
    MOVE_END = 123
def connect_wifi(addr=None,udid=None):
    """
    Args:
        addr (str) uiautomator server address.

    Returns:
        UIAutomatorServer

    Examples:
        connect_wifi("10.0.0.1")
    """
    if '://' not in addr:
        addr = 'http://' + addr
    if addr.startswith('http://'):
        u = urlparse.urlparse(addr)
        host = u.hostname
        port = u.port or 7912
        return UIAutomatorServer(host, port,udid)
    else:
        raise RuntimeError("address should start with http://")
def connect(udid=None):
    adb = adbutils.Adb(udid)
    lport = adb.forward_port(7912)
    d = connect_wifi('127.0.0.1:' + str(lport),udid)
    return d
class UIAutomatorServer(object):
    __isfrozen = False
    __plugins = {}

    def __init__(self, host, port=7912,udid=None):
        """
        Args:
            host (str): host address
            port (int): port number

        Raises:
            EnvironmentError
        """
        self._host = host
        self._port = port
        self._server_url = 'http://{}:{}'.format(host, port)
        self._server_jsonrpc_url = self._server_url + "/jsonrpc/0"
        self._default_session = Session(self, None)
        self._cached_plugins = {}
        self.__devinfo = None
        self.platform = None  # hot fix for weditor

        self.ash = Device(udid)  # the powerful adb shell
        self.e = Element(udid)
        self.wait_timeout = 20.0  # wait element timeout
        self.click_post_delay = None  # wait after each click
        self._freeze()  # prevent creating new attrs
        # self._atx_agent_check()

    def _freeze(self):
        self.__isfrozen = True

    @staticmethod
    def plugins():
        return UIAutomatorServer.__plugins

    def __setattr__(self, key, value):
        """ Prevent creating new attributes outside __init__ """
        if self.__isfrozen and not hasattr(self, key):
            raise TypeError("Key %s does not exist in class %r" % (key, self))
        object.__setattr__(self, key, value)

    def __str__(self):
        return 'uiautomator2 object for %s:%d' % (self._host, self._port)

    def __repr__(self):
        return str(self)

    @property
    def debug(self):
        return hasattr(self._reqsess, 'debug') and self._reqsess.debug

    @debug.setter
    def debug(self, value):
        self._reqsess.debug = bool(value)

    @property
    def serial(self):
        return self.shell(['getprop', 'ro.serialno'])

    @property
    def jsonrpc(self):
        """
        Make jsonrpc call easier
        For example:
            self.jsonrpc.pressKey("home")
        """
        return self.setup_jsonrpc()

    def path2url(self, path):
        return urlparse.urljoin(self._server_url, path)

    def window_size(self):
        """ return (width, height) """
        info = self.ash.getScreenResolution()
        w, h = info[0], info[1]
        return w, h

    def setup_jsonrpc(self, jsonrpc_url=None):
        """
        Wrap jsonrpc call into object
        Usage example:
            self.setup_jsonrpc().pressKey("home")
        """
        if not jsonrpc_url:
            jsonrpc_url = self._server_jsonrpc_url

        class JSONRpcWrapper():
            def __init__(self, server):
                self.server = server
                self.method = None

            def __getattr__(self, method):
                self.method = method  # jsonrpc function name
                return self

            def __call__(self, *args, **kwargs):
                http_timeout = kwargs.pop('http_timeout', HTTP_TIMEOUT)
                params = args if args else kwargs
                return self.server.jsonrpc_retry_call(jsonrpc_url, self.method,
                                                      params, http_timeout)

        return JSONRpcWrapper(self)

    def jsonrpc_retry_call(self, *args,
                           **kwargs):  # method, params=[], http_timeout=60):
        try:
            return self.jsonrpc_call(*args, **kwargs)
        except (GatewayError,):
            warnings.warn(
                "uiautomator2 is not reponding, restart uiautomator2 automatically",
                RuntimeWarning,
                stacklevel=1)
            return self.jsonrpc_call(*args, **kwargs)
        except UiAutomationNotConnectedError:
            warnings.warn(
                "UiAutomation not connected, restart uiautoamtor",
                RuntimeWarning,
                stacklevel=1)
            return self.jsonrpc_call(*args, **kwargs)
        except (NullObjectExceptionError,
                NullPointerExceptionError, StaleObjectExceptionError) as e:
            if args[1] != 'dumpWindowHierarchy':  # args[1] method
                warnings.warn(
                    "uiautomator2 raise exception %s, and run code again" % e,
                    RuntimeWarning,
                    stacklevel=1)
            time.sleep(1)
            return self.jsonrpc_call(*args, **kwargs)

    def jsonrpc_call(self, jsonrpc_url, method, params=[], http_timeout=60):
        """ 
        'http://127.0.0.1:59648/jsonrpc/0'
        'objInfo'
        <class 'tuple'>: ({'mask': 1, 'childOrSibling': [], 'childOrSiblingSelector': [], 'text': '设置'},)
        60
        """
        request_start = time.time()
        # {'method': 'objInfo', 'params': ({'mask': 1, 'childOrSibling': [], 'childOrSiblingSelector': [], 'text': '设置'},)}
        if method == 'click':
            return True
        elif method == 'injectInputEvent':
            return True
        else:
            params0 = params[0]
            attrib = sorted(params0)[-1]
            name = params0[attrib]
            if method == 'objInfo':
                return self.e.info(attrib,name)
            elif method == 'exist':
                return self.e.exists(attrib, name)
            elif method == 'waitUntilGone':
                time_out = params[1]/1000
                start_time = time.time()
                while time.time() - start_time < time_out:
                    if not self.e.exists(attrib, name):
                        return True
                return False
            elif method == 'waitForExists':
                time_out = params[1]/1000
                start_time = time.time()
                if self.e.exists(attrib, name):
                    return True
                while time.time() - start_time < time_out:
                    if self.e.exists(attrib, name):
                        return True
                return False
            elif method == 'setText':
                text = params[1]
                self.ash.click_element(self.e.d_right_corner(attrib, name))
                self.ash.clear_text(len(self.e.info(attrib, name)['text']))
                self.ash.setText(text)
                return True
            elif method == 'clearTextField':
                self.ash.click_element(self.e.d_right_corner(attrib, name))
                self.ash.clear_text(len(self.e.info(attrib, name)['text']))
                return True
            elif method == 'getText':
                return self.e.info(attrib, name)['text']

    def _jsonrpc_id(self, method):
        m = hashlib.md5()
        m.update(("%s at %f" % (method, time.time())).encode("utf-8"))
        return m.hexdigest()


    def app_install(self, url, installing_callback=None, server=None):
        """
        {u'message': u'downloading', "progress": {u'totalSize': 407992690, u'copiedSize': 49152}}

        Returns:
            packageName

        Raises:
            RuntimeError
        """
        r = self._reqsess.post(self.path2url('/install'), data={'url': url})
        if r.status_code != 200:
            raise RuntimeError("app install error:", r.text)
        id = r.text.strip()
        print(time.strftime('%H:%M:%S'), "id:", id)
        return self._wait_install_finished(id, installing_callback)

    def _wait_install_finished(self, id, installing_callback):
        bar = None
        downloaded = True

        while True:
            resp = self._reqsess.get(self.path2url('/install/' + id))
            resp.raise_for_status()
            jdata = resp.json()
            message = jdata['message']
            pg = jdata.get('progress')

            def notty_print_progress(pg):
                written = pg['copiedSize']
                total = pg['totalSize']
                print(
                    time.strftime('%H:%M:%S'), 'downloading %.1f%% [%s/%s]' %
                                               (100.0 * written / total,
                                                humanize.naturalsize(written, gnu=True),
                                                humanize.naturalsize(total, gnu=True)))

            if message == 'downloading':
                downloaded = False
                if pg:  # if there is a progress
                    if hasattr(sys.stdout, 'isatty'):
                        if sys.stdout.isatty():
                            if not bar:
                                bar = _ProgressBar(
                                    time.strftime('%H:%M:%S') + ' downloading',
                                    max=pg['totalSize'])
                            written = pg['copiedSize']
                            bar.next(written - bar.index)
                        else:
                            notty_print_progress(pg)
                    else:
                        pass
                else:
                    print(time.strftime('%H:%M:%S'), "download initialing")
            else:
                if not downloaded:
                    downloaded = True
                    if bar:  # bar only set in atty
                        bar.next(pg['copiedSize'] - bar.index) if pg else None
                        bar.finish()
                    else:
                        print(time.strftime('%H:%M:%S'), "download 100%")
                print(time.strftime('%H:%M:%S'), message)
            if message == 'installing':
                if callable(installing_callback):
                    installing_callback(self)
            if message == 'success installed':
                return jdata.get('packageName')

            if jdata.get('error'):
                raise RuntimeError("error", jdata.get('error'))

            try:
                time.sleep(1)
            except KeyboardInterrupt:
                bar.finish() if bar else None
                print("keyboard interrupt catched, cancel install id", id)
                self._reqsess.delete(self.path2url('/install/' + id))
                raise

    def shell(self, cmdargs, stream=False, timeout=60):
        if isinstance(cmdargs, (list, tuple)):
            cmdargs = list2cmdline(cmdargs)

        return self.ash.shell(cmdargs).stdout.read().strip().decode('utf8')

    def adb_shell(self, *args):
        """
        Example:
            adb_shell('pwd')
            adb_shell('ls', '-l')
            adb_shell('ls -l')

        Returns:
            string for stdout merged with stderr, after the entire shell command is completed.
        """
        # print(
        #     "DeprecatedWarning: adb_shell is deprecated, use: output, exit_code = shell(['ls', '-l']) instead"
        # )
        cmdline = args[0] if len(args) == 1 else list2cmdline(args)
        return self.shell(cmdline)[0]

    def app_start(self,
                  pkg_name,
                  activity=None,
                  extras={},
                  wait=True,
                  stop=False,
                  unlock=False):
        """ Launch application
        Args:
            pkg_name (str): package name
            activity (str): app activity
            stop (str): Stop app before starting the activity. (require activity)
        """
        if unlock:
            self.ash.screen_on()

        if activity:
            # -D: enable debugging
            # -W: wait for launch to complete
            # -S: force stop the target app before starting the activity
            # --user <USER_ID> | current: Specify which user to run as; if not
            #    specified then run as the current user.
            # -e <EXTRA_KEY> <EXTRA_STRING_VALUE>
            # --ei <EXTRA_KEY> <EXTRA_INT_VALUE>
            # --ez <EXTRA_KEY> <EXTRA_BOOLEAN_VALUE>
            args = ['am', 'start', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER']
            if wait:
                args.append('-W')
            if stop:
                args.append('-S')
            args += ['-n', '{}/{}'.format(pkg_name, activity)]
            # -e --ez
            extra_args = []
            for k, v in extras.items():
                if isinstance(v, bool):
                    extra_args.extend(['--ez', k, 'true' if v else 'false'])
                elif isinstance(v, int):
                    extra_args.extend(['--ei', k, str(v)])
                else:
                    extra_args.extend(['-e', k, v])
            args += extra_args
            # 'am', 'start', '-W', '-n', '{}/{}'.format(pkg_name, activity))
            self.shell(args)
        else:
            if stop:
                self.app_stop(pkg_name)
            self.shell([
                'monkey', '-p', pkg_name, '-c',
                'android.intent.category.LAUNCHER', '1'
            ])

    @property
    def current_app(self):
        """
        Returns:
            dict(package, activity, pid?)

        Raises:
            EnvironementError

        For developer:
            Function reset_uiautomator need this function, so can't use jsonrpc here.
        """
        _focusedRE = re.compile(
            r'mCurrentFocus=Window{\w+ \w+ (?P<package>.*)/(?P<activity>.*)\}')
        m = _focusedRE.search(self.shell(['dumpsys', 'window', 'windows']))
        if m:
            return dict(
                package=m.group('package'), activity=m.group('activity'))

        # try: adb shell dumpsys activity top
        _activityRE = re.compile(
            r'ACTIVITY (?P<package>[^/]+)/(?P<activity>[^/\s]+) \w+ pid=(?P<pid>\d+)'
        )
        output, _ = self.shell(['dumpsys', 'activity', 'top'])
        ms = _activityRE.finditer(output)
        ret = None
        for m in ms:
            ret = dict(
                package=m.group('package'),
                activity=m.group('activity'),
                pid=int(m.group('pid')))
        if ret:  # get last result
            return ret
        raise EnvironmentError("Couldn't get focused app")

    def app_stop(self, pkg_name):
        """ Stop one application: am force-stop"""
        self.shell(['am', 'force-stop', pkg_name])

    def app_stop_all(self, excludes=[]):
        """ Stop all third party applications
        Args:
            excludes (list): apps that do now want to kill

        Returns:
            a list of killed apps
        """
        our_apps = ['com.github.uiautomator', 'com.github.uiautomator.test']
        output, _ = self.shell(['pm', 'list', 'packages', '-3'])
        pkgs = re.findall('package:([^\s]+)', output)
        process_names = re.findall('([^\s]+)$', self.shell('ps')[0], re.M)
        kill_pkgs = set(pkgs).intersection(process_names).difference(
            our_apps + excludes)
        kill_pkgs = list(kill_pkgs)
        for pkg_name in kill_pkgs:
            self.app_stop(pkg_name)
        return kill_pkgs

    def app_clear(self, pkg_name):
        """ Stop and clear app data: pm clear """
        self.shell(['pm', 'clear', pkg_name])

    def app_uninstall(self, pkg_name):
        """ Uninstall an app """
        self.shell(["pm", "uninstall", pkg_name])

    def app_uninstall_all(self, excludes=[], verbose=False):
        """ Uninstall all apps """
        our_apps = ['com.github.uiautomator', 'com.github.uiautomator.test']
        output, _ = self.shell(['pm', 'list', 'packages', '-3'])
        pkgs = re.findall('package:([^\s]+)', output)
        pkgs = set(pkgs).difference(our_apps + excludes)
        pkgs = list(pkgs)
        for pkg_name in pkgs:
            if verbose:
                print("uninstalling", pkg_name)
            self.app_uninstall(pkg_name)
        return pkgs

    def _pidof_app(self, pkg_name):
        """
        Return pid of package name
        """
        text = self._reqsess.get(self.path2url('/pidof/' + pkg_name)).text
        if text.isdigit():
            return int(text)

    def push_url(self, url, dst, mode=0o644):
        """
        Args:
            url (str): http url address
            dst (str): destination
            mode (str): file mode

        Raises:
            FileNotFoundError(py3) OSError(py2)
        """
        modestr = oct(mode).replace('o', '')
        r = self._reqsess.post(
            self.path2url('/download'),
            data={
                'url': url,
                'filepath': dst,
                'mode': modestr
            })
        if r.status_code != 200:
            raise IOError("push-url", "%s -> %s" % (url, dst), r.text)
        key = r.text.strip()
        while 1:
            r = self._reqsess.get(self.path2url('/download/' + key))
            jdata = r.json()
            message = jdata.get('message')
            if message == 'downloaded':
                log_print("downloaded")
                break
            elif message == 'downloading':
                progress = jdata.get('progress')
                if progress:
                    copied_size = progress.get('copiedSize')
                    total_size = progress.get('totalSize')
                    log_print("{} {} / {}".format(
                        message, humanize.naturalsize(copied_size),
                        humanize.naturalsize(total_size)))
                else:
                    log_print("downloading")
            else:
                log_print("unknown json:" + str(jdata))
                raise IOError(message)
            time.sleep(1)

    def push(self, src, dst, mode=0o644):
        """
        Args:
            src (path or fileobj): source file
            dst (str): destination can be folder or file path

        Returns:
            dict object, for example:

                {"mode": "0660", "size": 63, "target": "/sdcard/ABOUT.rst"}

            Since chmod may fail in android, the result "mode" may not same with input args(mode)

        Raises:
            IOError(if push got something wrong)
        """
        modestr = oct(mode).replace('o', '')
        pathname = self.path2url('/upload/' + dst.lstrip('/'))
        if isinstance(src, six.string_types):
            src = open(src, 'rb')
        r = self._reqsess.post(
            pathname, data={'mode': modestr}, files={'file': src})
        if r.status_code == 200:
            return r.json()
        raise IOError("push", "%s -> %s" % (src, dst), r.text)

    def pull(self, src, dst):
        """
        Pull file from device to local

        Raises:
            FileNotFoundError(py3) OSError(py2)

        Require atx-agent >= 0.0.9
        """
        pathname = self.path2url("/raw/" + src.lstrip("/"))
        r = self._reqsess.get(pathname, stream=True)
        if r.status_code != 200:
            raise FileNotFoundError("pull", src, r.text)
        with open(dst, 'wb') as f:
            shutil.copyfileobj(r.raw, f)

    @property
    def screenshot_uri(self):
        return 'http://%s:%d/screenshot/0' % (self._host, self._port)

    @property
    def device_info(self):
        if self.__devinfo:
            return self.__devinfo
        d = self.ash
        device_info = d.get_device_info()
        getAndroidVersion = d.get_value('ro.build.version.release', device_info)
        get_brand = d.get_value('ro.boot.hardware', device_info)
        getSdkVersion = d.get_value('ro.build.version.sdk', device_info)
        getDeviceModel = d.get_value('ro.product.model', device_info)
        get_heapgrowthlimit = d.get_value('dalvik.vm.heapgrowthlimit', device_info)
        get_heapstartsize = d.get_value('dalvik.vm.heapstartsize', device_info)
        get_heapsize = d.get_value('dalvik.vm.heapsize', device_info)
        self.__devinfo = {'udid': d.getUdid(),'ip':d.ipAddress(),'mac':d.get_mac(),'model':getDeviceModel, 'version': getAndroidVersion, 'serialno': d.get_serialno(), 'brand': get_brand, 'sdk': getSdkVersion, 'display': d.getScreenResolution(),'battery':{'status': d.getBatteryStatus(), 'health': d.getBatteryHealth(), 'present': d.getBatteryPresent(), 'level': d.getBatteryLevel(), 'voltage': d.getBatteryVoltage(), 'temperature': d.getBatteryTemp()}, 'memory': {'total': d.getMemTotal(), 'free': d.getMemFree()}, 'cpu': {'cores': ' ', 'hardware': d.getCpuHardware()}}
        return self.__devinfo

    def session(self, pkg_name, attach=False):
        """
        Create a new session

        Args:
            pkg_name (str): android package name
            attach (bool): attach to already running app

        Raises:
            requests.HTTPError, SessionBrokenError
        """
        if pkg_name is None:
            return self._default_session

        if not attach:
            resp = self._reqsess.post(
                self.path2url("/session/" + pkg_name), data={"flags": "-W -S"})
            if resp.status_code == 410:  # Gone
                raise SessionBrokenError(pkg_name, resp.text)
            resp.raise_for_status()
            jsondata = resp.json()
            if not jsondata["success"]:
                raise SessionBrokenError("app launch failed",
                                         jsondata["error"], jsondata["output"])

            time.sleep(2.5)  # wait launch finished, maybe no need
        pid = self._pidof_app(pkg_name)
        if not pid:
            raise SessionBrokenError(pkg_name)
        return Session(self, pkg_name, pid)

    def __getattr__(self, attr):
        if attr in self._cached_plugins:
            return self._cached_plugins[attr]
        if attr.startswith('ext_'):
            if attr[4:] not in self.__plugins:
                raise ValueError("plugin \"%s\" not registed" % attr[4:])
            func, args, kwargs = self.__plugins[attr[4:]]
            obj = partial(func, self)(*args, **kwargs)
            self._cached_plugins[attr] = obj
            return obj
        try:
            return getattr(self._default_session, attr)
        except AttributeError:
            raise AttributeError("'Session or UIAutomatorServer' object has no attribute '%s'" % attr)

    def __call__(self, **kwargs):
        return self._default_session(**kwargs)
def check_alive(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        if not self.running():
            raise SessionBrokenError(self._pkg_name)
        return fn(self, *args, **kwargs)

    return inner
class Session(object):
    __orientation = (  # device orientation
        (0, "natural", "n", 0), (1, "left", "l", 90),
        (2, "upsidedown", "u", 180), (3, "right", "r", 270))

    def __init__(self, server, pkg_name=None, pid=None,udid=None):
        self.server = server
        self._pkg_name = pkg_name
        self._pid = pid
        self._jsonrpc = server.jsonrpc
        if pid and pkg_name:
            jsonrpc_url = server.path2url('/session/%d:%s/jsonrpc/0' %
                                          (pid, pkg_name))
            self._jsonrpc = server.setup_jsonrpc(jsonrpc_url)

        # hot fix for session missing shell function
        self.shell = self.server.shell
        self.d=Device(udid)

    def __repr__(self):
        if self._pid and self._pkg_name:
            return "<uiautomator2.Session pid:%d pkgname:%s>" % (
                self._pid, self._pkg_name)
        return super(Session, self).__repr__()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def implicitly_wait(self, seconds=None):
        """set default wait timeout
        Args:
            seconds(float): to wait element show up
        """
        if seconds is not None:
            self.server.wait_timeout = seconds
        return self.server.wait_timeout

    def close(self):
        """ close app """
        if self._pkg_name:
            self.server.app_stop(self._pkg_name)

    def running(self):
        """
        Check is session is running. return bool
        """
        if self._pid and self._pkg_name:
            ping_url = self.server.path2url('/session/%d:%s/ping' %
                                            (self._pid, self._pkg_name))
            return self.server._reqsess.get(ping_url).text.strip() == 'pong'
        # warnings.warn("pid and pkg_name is not set, ping will always return True", Warning, stacklevel=1)
        return True

    @property
    def jsonrpc(self):
        return self._jsonrpc

    @property
    def pos_rel2abs(self):
        size = []

        def convert(x, y):
            assert x >= 0
            assert y >= 0

            if (x < 1 or y < 1) and not size:
                size.extend(
                    self.server.window_size())  # size will be [width, height]

            if x < 1:
                x = int(size[0] * x)
            if y < 1:
                y = int(size[1] * y)
            return x, y

        return convert

    def make_toast(self, text, duration=1.0):
        """ Show toast
        Args:
            text (str): text to show
            duration (float): seconds of display
        """
        warnings.warn(
            "Use d.toast.show(text, duration) instead.",
            DeprecationWarning,
            stacklevel=2)
        return self.jsonrpc.makeToast(text, duration * 1000)

    @property
    def toast(self):
        obj = self

        class Toast(object):
            def get_message(self,
                            wait_timeout=10,
                            cache_timeout=10,
                            default=None):
                """
                Args:
                    wait_timeout: seconds of max wait time if toast now show right now
                    cache_timeout: return immediately if toast showed in recent $cache_timeout
                    default: default messsage to return when no toast show up

                Returns:
                    None or toast message
                """
                deadline = time.time() + wait_timeout
                while 1:
                    message = obj.jsonrpc.getLastToast(cache_timeout * 1000)
                    if message:
                        return message
                    if time.time() > deadline:
                        return default
                    time.sleep(.5)

            def reset(self):
                return obj.jsonrpc.clearLastToast()

            def show(self, text, duration=1.0):
                return obj.jsonrpc.makeToast(text, duration * 1000)

        return Toast()

    @check_alive
    def set_fastinput_ime(self, enable=True):
        """ Enable of Disable FastInputIME """
        fast_ime = 'com.github.uiautomator/.FastInputIME'
        if enable:
            self.server.shell(['ime', 'enable', fast_ime])
            self.server.shell(['ime', 'set', fast_ime])
        else:
            self.server.shell(['ime', 'disable', fast_ime])

    @check_alive
    def send_keys(self, text):
        """
        Raises:
            EnvironmentError
        """
        try:
            self.wait_fastinput_ime()
            base64text = base64.b64encode(text.encode('utf-8')).decode()
            self.server.shell([
                'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'text',
                base64text
            ])
            return True
        except EnvironmentError:
            warnings.warn(
                "set FastInputIME failed. use \"d(focused=True).set_text instead\"",
                Warning)
            return self(focused=True).set_text(text)
            # warnings.warn("set FastInputIME failed. use \"adb shell input text\" instead", Warning)
            # self.server.adb_shell("input", "text", text.replace(" ", "%s"))

    @check_alive
    def send_action(self, code):
        """
        Simulate input method edito code

        Args:
            code (str or int): input method editor code

        Examples:
            send_action("search"), send_action(3)

        Refs:
            https://developer.android.com/reference/android/view/inputmethod/EditorInfo
        """
        self.wait_fastinput_ime()
        __alias = {
            "go": 2,
            "search": 3,
            "send": 4,
            "next": 5,
            "done": 6,
            "previous": 7,
        }
        if isinstance(code, six.string_types):
            code = __alias.get(code, code)
        self.server.shell(['am', 'broadcast', '-a', 'ADB_EDITOR_CODE', '--ei', 'code', str(code)])

    @check_alive
    def clear_text(self):
        """ clear text
        Raises:
            EnvironmentError
        """
        try:
            self.wait_fastinput_ime()
            self.server.shell(['am', 'broadcast', '-a', 'ADB_CLEAR_TEXT'])
        except EnvironmentError:
            # for Android simulator
            self(focused=True).clear_text()

    def wait_fastinput_ime(self, timeout=5.0):
        """ wait FastInputIME is ready
        Args:
            timeout(float): maxium wait time
        Raises:
            EnvironmentError
        """
        if not self.server.serial:  # maybe simulator eg: genymotion, 海马玩模拟器
            raise EnvironmentError("Android simulator is not supported.")

        deadline = time.time() + timeout
        while time.time() < deadline:
            ime_id, shown = self.current_ime()
            if ime_id != "com.github.uiautomator/.FastInputIME":
                self.set_fastinput_ime(True)
                time.sleep(0.5)
                continue
            if shown:
                return True
            time.sleep(0.2)
        raise EnvironmentError("FastInputIME started failed")

    def current_ime(self):
        """ Current input method
        Returns:
            (method_id(str), shown(bool)

        Example output:
            ("com.github.uiautomator/.FastInputIME", True)
        """
        dim, _ = self.server.shell(['dumpsys', 'input_method'])
        m = _INPUT_METHOD_RE.search(dim)
        method_id = None if not m else m.group(1)
        shown = "mInputShown=true" in dim
        return (method_id, shown)

    def tap(self, x, y):
        """
        alias of click
        """
        self.click(x, y)

    @property
    def touch(self):
        """
        ACTION_DOWN: 0 ACTION_MOVE: 2
        touch.down(x, y)
        touch.move(x, y)
        touch.up()
        """
        ACTION_DOWN = 0
        ACTION_MOVE = 2
        ACTION_UP = 1

        obj = self

        class _Touch(object):
            def down(self, x, y):
                obj.jsonrpc.injectInputEvent(ACTION_DOWN, x, y, 0)

            def move(self, x, y):
                obj.jsonrpc.injectInputEvent(ACTION_MOVE, x, y, 0)

            def up(self, x, y):
                obj.jsonrpc.injectInputEvent(ACTION_UP, x, y, 0)

        return _Touch()

    def click(self, x, y):
        """
        click position
        """
        x, y = self.pos_rel2abs(x, y)
        self.d.click(x,y)
        ret = self.jsonrpc.click(x, y)
        if self.server.click_post_delay:  # click code delay
            time.sleep(self.server.click_post_delay)

    def double_click(self, x, y, duration=0.1):
        """
        double click position
        """
        x, y = self.pos_rel2abs(x, y)
        self.touch.down(x, y)
        self.touch.up(x, y)
        time.sleep(duration)
        self.click(x, y)  # use click last is for htmlreport

    def long_click(self, x, y, duration=None):
        '''long click at arbitrary coordinates.
        Args:
            duration (float): seconds of pressed
        '''
        if not duration:
            duration = 0.5
        x, y = self.pos_rel2abs(x, y)
        self.d.click_long(x,y,int(duration*1000))
        return self

    def swipe(self, fx, fy, tx, ty, duration=0.1, steps=None):
        """
        Args:
            fx, fy: from position
            tx, ty: to position
            duration (float): duration
            steps: 1 steps is about 5ms, if set, duration will be ignore

        Documents:
            uiautomator use steps instead of duration
            As the document say: Each step execution is throttled to 5ms per step.

        Links:
            https://developer.android.com/reference/android/support/test/uiautomator/UiDevice.html#swipe%28int,%20int,%20int,%20int,%20int%29
        """
        rel2abs = self.pos_rel2abs
        fx, fy = rel2abs(fx, fy)
        tx, ty = rel2abs(tx, ty)
        if not steps:
            steps = int(duration * 200)
        return self.jsonrpc.swipe(fx, fy, tx, ty, steps)

    def swipe_points(self, points, duration=0.5):
        """
        Args:
            points: is point array containg at least one point object. eg [[200, 300], [210, 320]]
            duration: duration to inject between two points

        Links:
            https://developer.android.com/reference/android/support/test/uiautomator/UiDevice.html#swipe(android.graphics.Point[], int)
        """
        ppoints = []
        rel2abs = self.pos_rel2abs
        for p in points:
            x, y = rel2abs(p[0], p[1])
            ppoints.append(x)
            ppoints.append(y)
        return self.jsonrpc.swipePoints(ppoints, int(duration * 200))

    def drag(self, sx, sy, ex, ey, duration=0.5):
        '''Swipe from one point to another point.'''
        rel2abs = self.pos_rel2abs
        sx, sy = rel2abs(sx, sy)
        ex, ey = rel2abs(ex, ey)
        return self.jsonrpc.drag(sx, sy, ex, ey, int(duration * 200))

    @retry(
        (IOError, SyntaxError), delay=.5, tries=5, jitter=0.1,
        max_delay=1)  # delay .5, .6, .7, .8 ...
    def screenshot(self, filename=None, format='pillow'):
        """
        Image format is JPEG

        Args:
            filename (str): saved filename
            format (string): used when filename is empty. one of "pillow" or "opencv"

        Raises:
            IOError, SyntaxError

        Examples:
            screenshot("saved.jpg")
            screenshot().save("saved.png")
            cv2.imwrite('saved.jpg', screenshot(format='opencv'))
        """
        r = requests.get(self.server.screenshot_uri, timeout=10)
        if filename:
            with open(filename, 'wb') as f:
                f.write(r.content)
            return filename
        elif format == 'pillow':
            from PIL import Image
            buff = io.BytesIO(r.content)
            return Image.open(buff)
        elif format == 'opencv':
            import cv2
            import numpy as np
            nparr = np.fromstring(r.content, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        elif format == 'raw':
            return r.content
        else:
            raise RuntimeError("Invalid format " + format)

    @retry(NullPointerExceptionError, delay=.5, tries=5, jitter=0.2)
    def dump_hierarchy(self, compressed=False, pretty=False):
        content = self.jsonrpc.dumpWindowHierarchy(compressed, None)
        if pretty and "\n " not in content:
            xml_text = xml.dom.minidom.parseString(content.encode("utf-8"))
            content = U(xml_text.toprettyxml(indent='  '))
        return content

    def freeze_rotation(self, freeze=True):
        '''freeze or unfreeze the device rotation in current status.'''
        self.jsonrpc.freezeRotation(freeze)

    def press(self, key, meta=None):
        """
        press key via name or key code. Supported key name includes:
            home, back, left, right, up, down, center, menu, search, enter,
            delete(or del), recent(recent apps), volume_up, volume_down,
            volume_mute, camera, power.
        """
        if isinstance(key, int):
            return self.jsonrpc.pressKeyCode(
                key, meta) if meta else self.server.jsonrpc.pressKeyCode(key)
        else:
            return self.jsonrpc.pressKey(key)

    def screen_on(self):
        self.jsonrpc.wakeUp()

    def screen_off(self):
        self.jsonrpc.sleep()

    @property
    def orientation(self):
        '''
        orienting the devie to left/right or natural.
        left/l:       rotation=90 , displayRotation=1
        right/r:      rotation=270, displayRotation=3
        natural/n:    rotation=0  , displayRotation=0
        upsidedown/u: rotation=180, displayRotation=2
        '''
        return self.__orientation[self.info["displayRotation"]][1]

    def set_orientation(self, value):
        '''setter of orientation property.'''
        for values in self.__orientation:
            if value in values:
                # can not set upside-down until api level 18.
                self.jsonrpc.setOrientation(values[1])
                break
        else:
            raise ValueError("Invalid orientation.")

    @property
    def last_traversed_text(self):
        '''get last traversed text. used in webview for highlighted text.'''
        return self.jsonrpc.getLastTraversedText()

    def clear_traversed_text(self):
        '''clear the last traversed text.'''
        self.jsonrpc.clearLastTraversedText()

    def open_notification(self):
        return self.jsonrpc.openNotification()

    def open_quick_settings(self):
        return self.jsonrpc.openQuickSettings()

    def exists(self, **kwargs):
        return self(**kwargs).exists

    def xpath(self, xpath, source=None):
        """
        Args:
            xpath: expression of XPath2.0
            source: optional, hierarchy from dump_hierarchy()

        Returns:
            XPathSelector
        """
        return XPathSelector(xpath, self.server, source)

    def watcher(self, name):
        obj = self

        class Watcher(object):
            def __init__(self):
                self.__selectors = []

            @property
            def triggered(self):
                return obj.server.jsonrpc.hasWatcherTriggered(name)

            def remove(self):
                obj.server.jsonrpc.removeWatcher(name)

            def when(self, **kwargs):
                self.__selectors.append(Selector(**kwargs))
                return self

            def click(self, **kwargs):
                target = Selector(**kwargs) if kwargs else self.__selectors[-1]
                obj.server.jsonrpc.registerClickUiObjectWatcher(
                    name, self.__selectors, target)

            def press(self, *keys):
                """
                key (str): on of
                    ("home", "back", "left", "right", "up", "down", "center",
                    "search", "enter", "delete", "del", "recent", "volume_up",
                    "menu", "volume_down", "volume_mute", "camera", "power")
                """
                obj.server.jsonrpc.registerPressKeyskWatcher(
                    name, self.__selectors, keys)

        return Watcher()

    @property
    def watchers(self):
        obj = self

        class Watchers(list):
            def __init__(self):
                for watcher in obj.server.jsonrpc.getWatchers():
                    self.append(watcher)

            @property
            def triggered(self):
                return obj.server.jsonrpc.hasAnyWatcherTriggered()

            def remove(self, name=None):
                if name:
                    obj.server.jsonrpc.removeWatcher(name)
                else:
                    for name in self:
                        obj.server.jsonrpc.removeWatcher(name)

            def reset(self):
                obj.server.jsonrpc.resetWatcherTriggers()
                return self

            def run(self):
                obj.server.jsonrpc.runWatchers()
                return self

            @property
            def watched(self):
                return obj.server.jsonrpc.hasWatchedOnWindowsChange()

            @watched.setter
            def watched(self, b):
                """
                Args:
                    b: boolean
                """
                assert isinstance(b, bool)
                obj.server.jsonrpc.runWatchersOnWindowsChange(b)

        return Watchers()

    @property
    def info(self):
        return self.jsonrpc.deviceInfo()

    def __call__(self, **kwargs):
        return UiObject(self, Selector(**kwargs))
class Selector(dict):
    """The class is to build parameters for UiSelector passed to Android device.
    """
    __fields = {
        "text": (0x01, None),  # MASK_TEXT,
        "textContains": (0x02, None),  # MASK_TEXTCONTAINS,
        "textMatches": (0x04, None),  # MASK_TEXTMATCHES,
        "textStartsWith": (0x08, None),  # MASK_TEXTSTARTSWITH,
        "className": (0x10, None),  # MASK_CLASSNAME
        "classNameMatches": (0x20, None),  # MASK_CLASSNAMEMATCHES
        "description": (0x40, None),  # MASK_DESCRIPTION
        "descriptionContains": (0x80, None),  # MASK_DESCRIPTIONCONTAINS
        "descriptionMatches": (0x0100, None),  # MASK_DESCRIPTIONMATCHES
        "descriptionStartsWith": (0x0200, None),  # MASK_DESCRIPTIONSTARTSWITH
        "checkable": (0x0400, False),  # MASK_CHECKABLE
        "checked": (0x0800, False),  # MASK_CHECKED
        "clickable": (0x1000, False),  # MASK_CLICKABLE
        "longClickable": (0x2000, False),  # MASK_LONGCLICKABLE,
        "scrollable": (0x4000, False),  # MASK_SCROLLABLE,
        "enabled": (0x8000, False),  # MASK_ENABLED,
        "focusable": (0x010000, False),  # MASK_FOCUSABLE,
        "focused": (0x020000, False),  # MASK_FOCUSED,
        "selected": (0x040000, False),  # MASK_SELECTED,
        "packageName": (0x080000, None),  # MASK_PACKAGENAME,
        "packageNameMatches": (0x100000, None),  # MASK_PACKAGENAMEMATCHES,
        "resourceId": (0x200000, None),  # MASK_RESOURCEID,
        "resourceIdMatches": (0x400000, None),  # MASK_RESOURCEIDMATCHES,
        "index": (0x800000, 0),  # MASK_INDEX,
        "instance": (0x01000000, 0)  # MASK_INSTANCE,
    }
    __mask, __childOrSibling, __childOrSiblingSelector = "mask", "childOrSibling", "childOrSiblingSelector"

    def __init__(self, **kwargs):
        super(Selector, self).__setitem__(self.__mask, 0)
        super(Selector, self).__setitem__(self.__childOrSibling, [])
        super(Selector, self).__setitem__(self.__childOrSiblingSelector, [])
        for k in kwargs:
            self[k] = kwargs[k]

    def __str__(self):
        """ remove useless part for easily debugger """
        selector = self.copy()
        selector.pop('mask')
        for key in ('childOrSibling', 'childOrSiblingSelector'):
            if not selector.get(key):
                selector.pop(key)
        args = []
        for (k, v) in selector.items():
            args.append(k + '=' + repr(v))
        return 'Selector [' + ', '.join(args) + ']'

    def __setitem__(self, k, v):
        if k in self.__fields:
            super(Selector, self).__setitem__(U(k), U(v))
            super(Selector, self).__setitem__(
                self.__mask, self[self.__mask] | self.__fields[k][0])
        else:
            raise ReferenceError("%s is not allowed." % k)

    def __delitem__(self, k):
        if k in self.__fields:
            super(Selector, self).__delitem__(k)
            super(Selector, self).__setitem__(
                self.__mask, self[self.__mask] & ~self.__fields[k][0])

    def clone(self):
        kwargs = dict((k, self[k]) for k in self if k not in [
            self.__mask, self.__childOrSibling, self.__childOrSiblingSelector
        ])
        selector = Selector(**kwargs)
        for v in self[self.__childOrSibling]:
            selector[self.__childOrSibling].append(v)
        for s in self[self.__childOrSiblingSelector]:
            selector[self.__childOrSiblingSelector].append(s.clone())
        return selector

    def child(self, **kwargs):
        self[self.__childOrSibling].append("child")
        self[self.__childOrSiblingSelector].append(Selector(**kwargs))
        return self

    def sibling(self, **kwargs):
        self[self.__childOrSibling].append("sibling")
        self[self.__childOrSiblingSelector].append(Selector(**kwargs))
        return self

    def update_instance(self, i):
        # update inside child instance
        if self[self.__childOrSiblingSelector]:
            self[self.__childOrSiblingSelector][-1]['instance'] = i
        else:
            self['instance'] = i
class Exists(object):
    """Exists object with magic methods."""

    def __init__(self, jsonrpc, selector):
        self.jsonrpc = jsonrpc
        self.selector = selector

    def __nonzero__(self):
        """Magic method for bool(self) python2 """
        return self.jsonrpc.exist(self.selector)

    def __bool__(self):
        """ Magic method for bool(self) python3 """
        return self.__nonzero__()

    def __call__(self, timeout=0):
        """Magic method for self(args).

        Args:
            timeout (float): exists in seconds
        """
        return self.jsonrpc.waitForExists(
            self.selector, timeout * 1000, http_timeout=timeout + 10)

    def __repr__(self):
        return str(bool(self))
class UiObject(object):
    def __init__(self, session, selector):
        self.session = session
        self.selector = selector
        self.jsonrpc = session.jsonrpc

    @property
    def wait_timeout(self):
        return self.session.server.wait_timeout

    @property
    def exists(self):
        '''check if the object exists in current window.'''
        return Exists(self.jsonrpc, self.selector)

    @property
    @retry(
        UiObjectNotFoundError, delay=.5, tries=3, jitter=0.1, logger=logging)
    def info(self):
        '''ui object info.'''
        return self.jsonrpc.objInfo(self.selector)

    def click(self, timeout=None, offset=None):
        """
        Click UI element. 

        Args:
            timeout: seconds wait element show up
            offset: (xoff, yoff) default (0.5, 0.5) -> center

        The click method does the same logic as java uiautomator does.
        1. waitForExists 2. get VisibleBounds center 3. send click event

        Raises:
            UiObjectNotFoundError
        """
        self.must_wait(timeout=timeout)
        x, y = self.center(offset=offset)
        # ext.htmlreport need to comment bellow code
        # if info['clickable']:
        #     return self.jsonrpc.click(self.selector)
        self.session.click(x, y)
        delay = self.session.server.click_post_delay
        if delay:
            time.sleep(delay)

    def center(self, offset=None):
        """
        Args:
            offset: optional, (x_off, y_off)
                (0, 0) means center, (0.5, 0.5) means right-bottom
        Return:
            center point (x, y)
        """
        info = self.info
        bound = info["bounds"]
        bound = bound.replace('[','').replace(']',',')
        bounds = bound.split(',')
        # lx, ly, rx, ry = bounds['left'], bounds['top'], bounds['right'], bounds['bottom']
        lx, ly, rx, ry = int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3])
        if not offset:
            offset = (0.5, 0.5)
        xoff, yoff = offset
        width, height = rx - lx, ry - ly
        x = lx + width * xoff
        y = ly + height * yoff
        return (x, y)

    # {'jsonrpc': '2.0', 'id': 'c97cd19e327541979283050322c2fcf9',
    #  'result': {'bounds': {'bottom': 1033, 'left': 360, 'right': 520, 'top': 833},
    #             'childCount': 0,
    #             'className': 'android.widget.TextView', 'contentDescription': '设置',
    #             'packageName': 'com.android.launcher', 'resourceName': None, 'text': '设置',
    #             'visibleBounds': {'bottom': 1033, 'left': 360, 'right': 520, 'top': 833},
    #             'checkable': False,
    #             'checked': False, 'clickable': True, 'enabled': True, 'focusable': True, 'focused': False,
    #             'longClickable': True, 'scrollable': False, 'selected': False}}
    # {'index': '6', 'text': '收款', 'resource-id': 'com.ccb.smartpos.bankpay:id/btn_home_pay',
    #  'class': 'android.widget.Button', 'package': 'com.ccb.smartpos.bankpay', 'content-desc': '', 'checkable': 'false',
    #  'checked': 'false', 'clickable': 'true', 'enabled': 'true', 'focusable': 'true', 'focused': 'false',
    #  'scrollable': 'false', 'long-clickable': 'false', 'password': 'false', 'selected': 'false',
    #  'bounds': '[20,654][700,774]'}

    def click_until_gone(self, maxretry=10, interval=1.0,time_out=20):
        """
        Click until element is gone

        Args:
            maxretry (int): max click times
            interval (float): sleep time between clicks

        Return:
            Bool if element is gone
        """
        self.click_exists(time_out)
        while maxretry > 0:
            time.sleep(interval)
            if not self.exists:
                return True
            self.click_exists(time_out)
            maxretry -= 1
        return False

    def click_exists(self, timeout=0):
        try:
            self.click(timeout=timeout)
            return True
        except UiObjectNotFoundError:
            return False

    def long_click(self, duration=None, timeout=None):
        """
        Args:
            duration (float): seconds of pressed
            timeout (float): seconds wait element show up
        """

        # if info['longClickable'] and not duration:
        #     return self.jsonrpc.longClick(self.selector)
        self.must_wait(timeout=timeout)
        x, y = self.center()
        return self.session.long_click(x, y, duration)

    def drag_to(self, *args, **kwargs):
        duration = kwargs.pop('duration', 0.5)
        timeout = kwargs.pop('timeout', None)
        self.must_wait(timeout=timeout)

        steps = int(duration * 200)
        if len(args) >= 2 or "x" in kwargs or "y" in kwargs:
            def drag2xy(x, y):
                x, y = self.session.pos_rel2abs(x,
                                                y)  # convert percent position
                return self.jsonrpc.dragTo(self.selector, x, y, steps)

            return drag2xy(*args, **kwargs)
        return self.jsonrpc.dragTo(self.selector, Selector(**kwargs), steps)

    def swipe(self, direction, steps=10):
        """
        Performs the swipe action on the UiObject.
        Swipe from center

        Args:
            direction (str): one of ("left", "right", "up", "down")
            steps (int): move steps, one step is about 5ms
            percent: float between [0, 1]

        Note: percent require API >= 18
        # assert 0 <= percent <= 1
        """
        assert direction in ("left", "right", "up", "down")

        self.must_wait()
        info = self.info
        bounds = info.get('visibleBounds') or info.get("bounds")
        lx, ly, rx, ry = bounds['left'], bounds['top'], bounds['right'], bounds['bottom']
        cx, cy = (lx + rx) // 2, (ly + ry) // 2
        if direction == 'up':
            self.session.swipe(cx, cy, cx, ly, steps=steps)
        elif direction == 'down':
            self.session.swipe(cx, cy, cx, ry - 1, steps=steps)
        elif direction == 'left':
            self.session.swipe(cx, cy, lx, cy, steps=steps)
        elif direction == 'right':
            self.session.swipe(cx, cy, rx - 1, cy, steps=steps)

            # return self.jsonrpc.swipe(self.selector, direction, percent, steps)

    def gesture(self, start1, start2, end1, end2, steps=100):
        '''
        perform two point gesture.
        Usage:
        d().gesture(startPoint1, startPoint2, endPoint1, endPoint2, steps)
        '''
        rel2abs = self.session.pos_rel2abs

        def point(x=0, y=0):
            x, y = rel2abs(x, y)
            return {"x": x, "y": y}

        def ctp(pt):
            return point(*pt) if type(pt) == tuple else pt

        s1, s2, e1, e2 = ctp(start1), ctp(start2), ctp(end1), ctp(end2)
        return self.jsonrpc.gesture(self.selector, s1, s2, e1, e2, steps)

    def pinch_in(self, percent=100, steps=50):
        return self.jsonrpc.pinchIn(self.selector, percent, steps)

    def pinch_out(self, percent=100, steps=50):
        return self.jsonrpc.pinchOut(self.selector, percent, steps)

    def wait(self, exists=True, timeout=20):
        """
        Wait until UI Element exists or gone

        Args:
            timeout (float): wait element timeout

        Example:
            d(text="Clock").wait()
            d(text="Settings").wait("gone") # wait until it's gone
        """
        if timeout is None:
            timeout = self.wait_timeout
        http_wait = timeout + 10
        if exists:
            return self.jsonrpc.waitForExists(
                self.selector, int(timeout * 1000), http_timeout=http_wait)
        else:
            return self.jsonrpc.waitUntilGone(
                self.selector, int(timeout * 1000), http_timeout=http_wait)

    def wait_gone(self, timeout=None):
        """ wait until ui gone
        Args:
            timeout (float): wait element gone timeout
        """
        timeout = timeout or self.wait_timeout
        return self.wait(exists=False, timeout=timeout)

    def must_wait(self, exists=True, timeout=None):
        """ wait and if not found raise UiObjectNotFoundError """
        if not self.wait(exists, timeout):
            raise UiObjectNotFoundError({'code': -32002, 'method': 'wait'})

    def send_keys(self, text):
        """ alias of set_text """
        return self.set_text(text)

    def set_text(self, text, timeout=None):
        self.must_wait(timeout=timeout)
        if not text:
            return self.jsonrpc.clearTextField(self.selector)
        else:
            return self.jsonrpc.setText(self.selector, text)

    def get_text(self, timeout=None):
        """ get text from field """
        self.must_wait(timeout=timeout)
        return self.jsonrpc.getText(self.selector)

    def clear_text(self, timeout=None):
        self.must_wait(timeout=timeout)
        return self.set_text(None)

    def child(self, **kwargs):
        return UiObject(self.session, self.selector.clone().child(**kwargs))

    def sibling(self, **kwargs):
        return UiObject(self.session, self.selector.clone().sibling(**kwargs))

    child_selector, from_parent = child, sibling

    def child_by_text(self, txt, **kwargs):
        if "allow_scroll_search" in kwargs:
            allow_scroll_search = kwargs.pop("allow_scroll_search")
            name = self.jsonrpc.childByText(self.selector, Selector(**kwargs),
                                            txt, allow_scroll_search)
        else:
            name = self.jsonrpc.childByText(self.selector, Selector(**kwargs),
                                            txt)
        return UiObject(self.session, name)

    def child_by_description(self, txt, **kwargs):
        # need test
        if "allow_scroll_search" in kwargs:
            allow_scroll_search = kwargs.pop("allow_scroll_search")
            name = self.jsonrpc.childByDescription(self.selector,
                                                   Selector(**kwargs), txt,
                                                   allow_scroll_search)
        else:
            name = self.jsonrpc.childByDescription(self.selector,
                                                   Selector(**kwargs), txt)
        return UiObject(self.session, name)

    def child_by_instance(self, inst, **kwargs):
        # need test
        return UiObject(self.session,
                        self.jsonrpc.childByInstance(self.selector,
                                                     Selector(**kwargs), inst))

    def parent(self):
        # android-uiautomator-server not implemented
        # In UIAutomator, UIObject2 has getParent() method
        # https://developer.android.com/reference/android/support/test/uiautomator/UiObject2.html
        raise NotImplementedError()
        return UiObject(self.session, self.jsonrpc.getParent(self.selector))

    def __getitem__(self, index):
        selector = self.selector.clone()
        selector.update_instance(index)
        return UiObject(self.session, selector)

    @property
    def count(self):
        return self.jsonrpc.count(self.selector)

    def __len__(self):
        return self.count

    def __iter__(self):
        obj, length = self, self.count

        class Iter(object):
            def __init__(self):
                self.index = -1

            def next(self):
                self.index += 1
                if self.index < length:
                    return obj[self.index]
                else:
                    raise StopIteration()

            __next__ = next

        return Iter()

    def right(self, **kwargs):
        def onrightof(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect2["left"] - rect1["right"] if top < bottom else -1

        return self.__view_beside(onrightof, **kwargs)

    def left(self, **kwargs):
        def onleftof(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect1["left"] - rect2["right"] if top < bottom else -1

        return self.__view_beside(onleftof, **kwargs)

    def up(self, **kwargs):
        def above(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect1["top"] - rect2["bottom"] if left < right else -1

        return self.__view_beside(above, **kwargs)

    def down(self, **kwargs):
        def under(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect2["top"] - rect1["bottom"] if left < right else -1

        return self.__view_beside(under, **kwargs)

    def __view_beside(self, onsideof, **kwargs):
        bounds = self.info["bounds"]
        min_dist, found = -1, None
        for ui in UiObject(self.session, Selector(**kwargs)):
            dist = onsideof(bounds, ui.info["bounds"])
            if dist >= 0 and (min_dist < 0 or dist < min_dist):
                min_dist, found = dist, ui
        return found

    @property
    def fling(self):
        """
        Args:
            dimention (str): one of "vert", "vertically", "vertical", "horiz", "horizental", "horizentally"
            action (str): one of "forward", "backward", "toBeginning", "toEnd", "to"
        """
        jsonrpc = self.jsonrpc
        selector = self.selector

        class _Fling(object):
            def __init__(self):
                self.vertical = True
                self.action = 'forward'

            def __getattr__(self, key):
                if key in ["horiz", "horizental", "horizentally"]:
                    self.vertical = False
                    return self
                if key in ['vert', 'vertically', 'vertical']:
                    self.vertical = True
                    return self
                if key in [
                    "forward", "backward", "toBeginning", "toEnd", "to"
                ]:
                    self.action = key
                    return self
                raise ValueError("invalid prop %s" % key)

            def __call__(self, max_swipes=500, **kwargs):
                if self.action == "forward":
                    return jsonrpc.flingForward(selector, self.vertical)
                elif self.action == "backward":
                    return jsonrpc.flingBackward(selector, self.vertical)
                elif self.action == "toBeginning":
                    return jsonrpc.flingToBeginning(selector, self.vertical,
                                                    max_swipes)
                elif self.action == "toEnd":
                    return jsonrpc.flingToEnd(selector, self.vertical,
                                              max_swipes)

        return _Fling()

    @property
    def scroll(self):
        """
        Args:
            dimention (str): one of "vert", "vertically", "vertical", "horiz", "horizental", "horizentally"
            action (str): one of "forward", "backward", "toBeginning", "toEnd", "to"
        """
        selector = self.selector
        jsonrpc = self.jsonrpc

        class _Scroll(object):
            def __init__(self):
                self.vertical = True
                self.action = 'forward'

            def __getattr__(self, key):
                if key in ["horiz", "horizental", "horizentally"]:
                    self.vertical = False
                    return self
                if key in ['vert', 'vertically', 'vertical']:
                    self.vertical = True
                    return self
                if key in [
                    "forward", "backward", "toBeginning", "toEnd", "to"
                ]:
                    self.action = key
                    return self
                raise ValueError("invalid prop %s" % key)

            def __call__(self, steps=20, max_swipes=500, **kwargs):
                if self.action in ["forward", "backward"]:
                    method = jsonrpc.scrollForward if self.action == "forward" else jsonrpc.scrollBackward
                    return method(selector, self.vertical, steps)
                elif self.action == "toBeginning":
                    return jsonrpc.scrollToBeginning(selector, self.vertical,
                                                     max_swipes, steps)
                elif self.action == "toEnd":
                    return jsonrpc.scrollToEnd(selector, self.vertical,
                                               max_swipes, steps)
                elif self.action == "to":
                    return jsonrpc.scrollTo(selector, Selector(**kwargs),
                                            self.vertical)

        return _Scroll()
class Device(object):
    """
    单个设备，可不传入参数device_id
    """
    def __init__(self, device_id=""):
        if device_id == "":
            self.device_id = ""
        else:
            self.device_id = "-s %s" % device_id

    # 当前时间
    def get_time(self):
        return time.strftime("%Y-%m-%d %H-%M-%S", time.localtime())

    def get_time_day(self):
        return time.strftime("%Y-%m-%d", time.localtime())

    # 时间戳 + str
    def print_before(self, str):
        print('%s %s' % (self.get_time(), str))

    # 时间戳 + str1 + str2
    def print_str(self, str1, str2):
        print('%s %s%s' % (self.get_time(), str1, str2))

    # adb命令
    def adb(self, args):
        cmd = "%s %s %s" % (command, self.device_id, str(args))
        return subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # adb 命令,返回运行结果
    def adb_return(self, args):
        cmd = "%s %s %s" % (command, self.device_id, str(args))
        return subprocess.check_output(cmd).decode('utf8')

    # adb shell命令
    def shell(self, args):
        cmd = "%s %s shell %s" % (command, self.device_id, str(args))
        return subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # adb shell命令,返回运行结果
    def shell_return(self, args):
        cmd = "%s %s shell %s" % (command, self.device_id, str(args))
        return subprocess.check_output(cmd).decode('utf8')
    # 获取udid ，判断设备是否连接
    def getUdid(self):
        try:
            '''''获取设备列表信息，并用"\r\n"拆分'''
            deviceInfo = self.adb_return('devices').split("\r\n")
            adb_first_start = False
            for i in deviceInfo:
                if 'successfully' in i:
                    adb_first_start = True
                    break
            if adb_first_start:
                udid = 'device'.join(deviceInfo[3].split('device')[:1])
                '''''如果没有链接设备或者设备读取失败，第二个元素为空'''
                if deviceInfo[3] == '':
                    return ''
                else:
                    return udid.strip()
            else:
                udid = 'device'.join(deviceInfo[1].split('device')[:1])
                '''''如果没有链接设备或者设备读取失败，第二个元素为空'''
                if deviceInfo[1] == '':
                    return ''
                else:
                    return udid.strip()
        except MyError as e:
            print("Device Connect Fail:", e.value)
    def getDeviceState(self):
        """
        获取设备状态： offline | bootloader | device
        """
        return self.adb("get-state").stdout.read().strip().decode('utf8')

    def get_serialno(self):
        """
        获取设备id号，return serialNo
        """
        return self.adb("get-serialno").stdout.read().strip().decode('utf8')

    def get_value(self,value, str):
        '''
        按照指定格式拿出值
        usage:  packages = "package:com.github.uiautomator package:com.netease.atx.assistant"
                version0 = "name=tool.terminal.apphelperservice versionCode=1000002 versionName=1.0.2"
                get_value('name',version0)
                结果：tool.terminal.apphelperservice
        :param str: 
        :return: 
        '''
        if '=\'' in str:
            name = '%s=\'' % (value).join(str.split('%s=\'' % (value))[1:])
            name = '\''.join(name.split('\'')[:1])
        else:
            name = '%s=' % (value).join(str.split('%s=' % (value))[1:])
            name = ' '.join(name.split(' ')[:1])
            if name[-1:] == '=':
                name = name[:-1]
        return name
    # 获取设备信息，大方法
    def get_device_info(self):
        device_info = self.shell("getprop").stdout.read().strip().decode('utf8').replace('\r\r\n',',').replace('[','').replace(']','').replace(':','=').replace(' ','')
        device_info = device_info.replace(',',' ')

        '''
        usage:如下所示
        
        getAndroidVersion = self.get_value('ro.build.version.release',device_info)
        get_brand = self.get_value('ro.boot.hardware',device_info)
        getSdkVersion = self.get_value('ro.build.version.sdk',device_info)
        getDeviceModel = self.get_value('ro.product.model',device_info)
        get_heapgrowthlimit = self.get_value('dalvik.vm.heapgrowthlimit',device_info)
        get_heapstartsize = self.get_value('dalvik.vm.heapstartsize',device_info)
        get_heapsize = self.get_value('dalvik.vm.heapsize',device_info)
        '''
        return device_info
    def getAndroidVersion(self):
        """
        获取设备中的Android版本号，如4.2.2
        """
        return self.shell("getprop ro.build.version.release").stdout.read().strip().decode('utf8')

    def get_brand(self):
        """
        获取Android平台型号品牌
        """
        return self.shell("getprop ro.boot.hardware").stdout.read().strip().decode('utf8')

    def getSdkVersion(self):
        """
        获取设备SDK版本号
        """
        return self.shell("getprop ro.build.version.sdk").stdout.read().strip().decode('utf8')

    def getDeviceModel(self):
        """
        获取设备型号
        """
        return self.shell("getprop ro.product.model").stdout.read().strip().decode('utf8')

    def getPid(self, packageName):
        """
        获取进程pid
        args:
        - packageName -: 应用包名
        usage: getPid("com.android.settings")
        """
        if system is "Windows":
            pidinfo = self.shell("ps | findstr %s$" % packageName).stdout.read().decode('utf8')
        else:
            pidinfo = self.shell("ps | grep -w %s" % packageName).stdout.read().decode('utf8')

        if pidinfo == '':
            return "the process doesn't exist."

        pattern = re.compile(r"\d+")
        result = pidinfo.split(" ")
        result.remove(result[0])

        return pattern.findall(" ".join(result))[0]

    def killProcess(self, pid):
        """
        杀死应用进程
        args:
        - pid -: 进程pid值
        usage: killProcess(154)
        注：杀死系统应用进程需要root权限
        """
        if self.shell_return("kill %s" % str(pid)).split(": ")[-1] == "":
            return "kill success"
        else:
            return self.shell_return("kill %s" % str(pid))  # .split(": ")[-1]

    def force_stop(self, packageName):
        """
        退出app，类似于kill掉进程
        usage: quitApp("com.android.settings")
        """
        self.shell("am force-stop %s" % packageName)

    def getFocusedPackageAndActivity(self):
        """
        获取当前应用界面的包名和Activity，返回的字符串格式为：packageName/activityName
        """
        pattern = re.compile(r"[a-zA-Z0-9\.]+/.[a-zA-Z0-9\.]+")
        out = self.shell("dumpsys window w | %s \/ | %s name=" % (find_util, find_util)).stdout.read()

        return pattern.findall(out.decode('utf8'))[0]

    def getCurrentPackageName(self):
        """
        获取当前运行的应用的包名
        """
        return self.getFocusedPackageAndActivity().split("/")[0]

    def getCurrentActivity(self):
        """
        获取当前运行应用的activity
        """
        return self.getFocusedPackageAndActivity().split("/")[-1]
    def getMemTotal(self):
        """
        获取最大内存
        """
        MemTotal = self.shell("cat proc/meminfo | %s MemTotal" % find_util).stdout.read().decode('utf8').split(":")[-1]

        return MemTotal.replace('\r\r\n','').strip()
    def getMemFree(self):
        """
        获取剩余内存
        """
        MemFree = self.shell("cat proc/meminfo | %s MemFree" % find_util).stdout.read().decode('utf8').split(":")[-1]

        return MemFree.replace('\r\r\n','').strip()
    def getCpuHardware(self):
        """
        获取剩余内存
        """
        Hardware = self.shell("cat proc/cpuinfo | %s Hardware" % find_util).stdout.read().decode('utf8').split(":")[-1]

        return Hardware.replace('\r\r\n','').strip()
    def getBatteryLevel(self):
        """
        获取电池电量
        """
        level = self.shell("dumpsys battery | %s level" % find_util).stdout.read().decode('utf8').split(": ")[-1]

        return int(level)
    def getBatteryVoltage(self):
        """
        获取电池电压
        """
        voltage = self.shell("dumpsys battery | %s voltage" % find_util).stdout.read().decode('utf8').split(": ")[-1]

        return int(voltage)

    def getBatteryHealth(self):
        """
        电池健康状态：只有数字2表示good
        """
        health = self.shell("dumpsys battery | %s health" % find_util).stdout.read().decode('utf8').split(": ")[-1]

        return int(health)
    def getBatteryACpowered(self):
        """
        电池是否在AC充电器充电
        """
        ACpowered = self.shell("dumpsys battery | %s AC" % find_util).stdout.read().decode('utf8').split(": ")[-1]

        return ACpowered.replace('\r\r\n','')
    def getBatteryPresent(self):
        """
        电池是否安装在机身
        """
        present = self.shell("dumpsys battery | %s present" % find_util).stdout.read().decode('utf8').split(": ")[-1]

        return present.replace('\r\r\n','')

    def getBatteryStatus(self):
        """
        获取电池充电状态 #电池状态：2：充电状态 ，其他数字为非充电状态
        BATTERY_STATUS_UNKNOWN：未知状态
        BATTERY_STATUS_CHARGING: 充电状态
        BATTERY_STATUS_DISCHARGING: 放电状态
        BATTERY_STATUS_NOT_CHARGING：未充电
        BATTERY_STATUS_FULL: 充电已满
        """
        statusDict = {1: "BATTERY_STATUS_UNKNOWN:未知状态",
                      2: "BATTERY_STATUS_CHARGING:充电状态",
                      3: "BATTERY_STATUS_DISCHARGING:放电状态",
                      4: "BATTERY_STATUS_NOT_CHARGING:未充电",
                      5: "BATTERY_STATUS_FULL:充电已满"}
        status = self.shell("dumpsys battery | %s status" % find_util).stdout.read().decode('utf8').split(": ")[-1]

        return statusDict[int(status)]

    def getBatteryTemp(self):
        """
        获取电池温度
        """
        temp = self.shell("dumpsys battery | %s temperature" % find_util).stdout.read().decode('utf8').split(": ")[-1]

        return int(temp) / 10.0

    def get_heapgrowthlimit(self):
        """
        单个应用程序最大内存限制，超过这个值会产生OOM(内存溢出）
        测程序一般看这个
        """
        heapgrowthlimit = self.shell("getprop dalvik.vm.heapgrowthlimit").stdout.read().decode('utf8').split("\r\r\n")[0]
        return heapgrowthlimit
    def get_heapstartsize(self):
        """
        应用启动后分配的初始内存
        """
        heapstartsize = self.shell("getprop dalvik.vm.heapstartsize").stdout.read().decode('utf8').split("\r\r\n")[0]
        return heapstartsize
    def get_heapsize(self):
        """
        单个java虚拟机最大的内存限制，超过这个值会产生OOM(内存溢出）
        """
        heapsize = self.shell("getprop dalvik.vm.heapsize").stdout.read().decode('utf8').split("\r\r\n")[0]
        return heapsize

    def getScreenResolution(self):
        """
        获取设备屏幕分辨率，return (width, high)
        """
        pattern = re.compile(r"\d+")
        out = self.shell("dumpsys display | %s PhysicalDisplayInfo" % find_util).stdout.read()
        # print(type(out))
        display = ""
        if out:
            display = pattern.findall(out.decode('utf-8'))
        elif int(self.getSdkVersion()) >= 18:
            display = self.shell("wm size").stdout.read().decode('utf8').split(":")[-1].strip().split("x")
        else:
            raise Exception("get screen resolution failed!")
        return (int(display[0]), int(display[1]))

    def screenshot(self, fileName=None):
        """
        截图，保存到脚本目录
        usage: adb.screenchot('screenshot.png')
        win 7不自动创建文件夹，所有要先判断然后创建
        """
        if not os.path.exists('tmp//screenshot'):
            os.makedirs('tmp//screenshot', exist_ok=True)
        self.shell("/system/bin/screencap -p /sdcard/screenshot.png").stdout.read().decode('utf8')
        self.adb("pull /sdcard/screenshot.png tmp/screenshot/%s" % (fileName if fileName != '' else 'screenshot.png')).stdout.read().decode('utf8')

    def reboot(self):
        """
        重启设备
        """
        self.adb("reboot")

    def fastboot(self):
        """
        进入fastboot模式
        """
        self.adb("reboot bootloader")

    def getSystemAppList(self):
        """
        获取设备中安装的系统应用包名列表
        """
        sysApp = []
        for packages in self.shell("pm list packages -s").stdout.readlines():
            sysApp.append(packages.decode('utf8').split(":")[-1].splitlines()[0])

        return sysApp

    def getThirdAppList(self):
        """
        获取设备中安装的第三方应用包名列表
        """
        thirdApp = []
        for packages in self.shell("pm list packages -3").stdout.readlines():
            thirdApp.append(packages.decode('utf8').split(":")[-1].splitlines()[0])

        return thirdApp

    def getMatchingAppList(self, keyword):
        """
        模糊查询与keyword匹配的应用包名列表
        usage: getMatchingAppList("qq")
        """
        matApp = []
        for packages in self.shell("pm list packages %s" % keyword).stdout.readlines():
            matApp.append(packages.decode('utf8').split(":")[-1].splitlines()[0])

        return matApp

    def getAppStartTotalTime(self, component):
        """
        获取启动应用所花时间
        usage: getAppStartTotalTime("com.android.settings/.Settings")
        """
        time = self.shell("am start -W %s | %s TotalTime" % (component, find_util)) \
            .stdout.read().decode('utf8').split(": ")[-1]
        return int(time)

    def installApp(self, appFile):
        """
        安装app，app名字不能含中文字符
        args:
        - appFile -: app路径
        usage: install("d:\\apps\\Weico.apk")
        """
        self.adb("install %s" % appFile)

    def isInstall(self, packageName):
        """
        判断应用是否安装，已安装返回True，否则返回False
        usage: isInstall("com.example.apidemo")
        """
        if self.getMatchingAppList(packageName):
            return True
        else:
            return False

    def uninstallApp(self, packageName):
        """
        卸载应用
        args:
        - packageName -:应用包名，非apk名
        """
        self.adb("uninstall %s" % packageName)

    def clearAppData(self, packageName):
        """
        清除应用用户数据
        usage: clearAppData("com.android.contacts")
        """
        if "Success" in self.shell_return("pm clear %s" % packageName):
            return "clear user data success "
        else:
            return "make sure package exist"

    def clearCurrentApp(self):
        """
        清除当前应用缓存数据
        """
        packageName = self.getCurrentPackageName()
        component = self.getFocusedPackageAndActivity()
        self.clearAppData(packageName)
        self.startActivity(component)

    def startActivity(self, component):
        """
        启动一个Activity
        usage: startActivity(component = "com.android.settinrs/.Settings")
        """
        self.shell("am start -n %s" % component)
    def start_app(self, packageName):
        """
        启动一个应用
        usage: start_app(packageName = "com.android.settings")
        """
        self.shell("monkey -p %s -c android.intent.category.LAUNCHER 1" % packageName)

    def startWebpage(self, url):
        """
        使用系统默认浏览器打开一个网页
        usage: startWebpage("http://www.baidu.com")
        """
        self.shell_return("am start -a android.intent.action.VIEW -d %s" % url)

    def callPhone(self, number):
        """
        启动拨号器拨打电话
        usage: callPhone(10086)
        """
        self.shell("am start -a android.intent.action.CALL -d tel:%s" % str(number))

    def sendKeyEvent(self, keycode):
        """
        发送一个按键事件
        args:
        - keycode -:
        http://developer.android.com/reference/android/view/KeyEvent.html
        usage: sendKeyEvent(keycode.HOME)
        """
        self.shell_return("input keyevent %s" % str(keycode))

    def longPressKey(self, keycode):
        """
        发送一个按键长按事件，Android 4.4以上
        usage: longPressKey(keycode.HOME)
        """
        self.shell("input keyevent --longpress %s" % str(keycode))

    def click_element(self, element):
        """
        点击元素
        usage: touchByElement(Element().findElementByName(u"计算器"))
        """
        self.shell("input tap %s %s" % (str(element[0]), str(element[1])))

    def click(self, x, y):
        """
        发送触摸点击事件
        usage: click(0.5, 0.5) 点击屏幕中心位置
        """
        if x < 1:
            self.shell("input tap %s %s" % (
            str(x * self.getScreenResolution()[0]), str(y * self.getScreenResolution()[1])))
        else:
            self.shell("input tap %s %s" % (x, y))

    def swipe(self, start_ratioWidth, start_ratioHigh, end_ratioWidth, end_ratioHigh, duration=" "):
        """
        发送滑动事件，Android 4.4以上可选duration(ms)
        usage: swipe(0.9, 0.5, 0.1, 0.5) 左滑
        """
        if start_ratioWidth < 1:
            self.shell("input swipe %s %s %s %s %s" % (
            str(start_ratioWidth * self.getScreenResolution()[0]), str(start_ratioHigh * self.getScreenResolution()[1]), \
            str(end_ratioWidth * self.getScreenResolution()[0]), str(end_ratioHigh * self.getScreenResolution()[1]),
            str(duration)))
        elif start_ratioWidth >= 1:
            self.shell("input swipe %s %s %s %s %s" % (
            start_ratioWidth, start_ratioHigh, end_ratioWidth, end_ratioHigh, str(duration)))

    def swipeToLeft(self):
        """
        左滑屏幕
        """
        self.swipe(0.8, 0.5, 0.2, 0.5)

    def swipeToRight(self):
        """
        右滑屏幕
        """
        self.swipe(0.2, 0.5, 0.8, 0.5)

    def swipeToUp(self):
        """
        上滑屏幕
        """
        self.swipe(0.5, 0.8, 0.5, 0.2)

    def swipeToDown(self):
        """
        下滑屏幕
        """
        self.swipe(0.5, 0.2, 0.5, 0.8)

    def click_long(self, x, y,duration=None):
        """
        长按屏幕的某个坐标位置, Android 4.4
        usage: click_long(500, 600)
               click_long(0.5, 0.5)
        """
        self.swipe(x, y, x, y, duration=duration if duration else 2000)

    def longPressElement(self, e):
        """
       长按元素, Android 4.4
        """
        self.shell("input swipe %s %s %s %s %s" % (str(e[0]), str(e[1]), str(e[0]), str(e[1]), str(2000)))

    # 删除文本框内容，入参：删除次数
    def clear_text(self, number):
        if not number:
            self.sendKeyEvent(keycode=67)
        else:
            for i in range(number):
                self.sendKeyEvent(keycode=67)

    def setText(self, string):
        """
        发送一段文本，只能包含英文字符和空格
        usage: setText("i am unique")
        """
        self.shell('input text "%s"' % (string))

    # 获取内存,并写入到txt中记录
    def get_meminfo_heap(self, packageName):
        if not os.path.exists("tmp//meminfo"):
            os.makedirs("tmp//meminfo", exist_ok=True)
        if packageName != '':
            Native_Heap = self.shell_return('dumpsys meminfo %s | grep Native' % (packageName)).split('\r\n')[0].strip()
            g = open('tmp/meminfo/%s的Native层内存使用情况%s.txt' % (packageName, self.get_time()[:10]), 'a')
            g.write('%s\n' % (Native_Heap))
            g.close()
            Dalvik_Heap = self.shell_return('dumpsys meminfo %s | grep Dalvik' % (packageName)).split('\r\n')[0].strip()
            g = open('tmp/meminfo/%s的Java    堆内存使用情况%s.txt' % (packageName, self.get_time()[:10]), 'a')
            g.write('%s\n' % (Dalvik_Heap))
            g.close()
        else:
            RAM_Used = self.shell_return('dumpsys meminfo | grep Used').split('\r\n')[0].strip()
            g = open('tmp/meminfo/全部内存情况%s.txt' % (self.get_time()[:10]), 'a')
            g.write('%s\n' % (RAM_Used))
            g.close()
            # top6 = self.shell_return('top -m 6 -n 1').split('\r\n')[0].strip()
            # g = open('tmp/meminfo/全部top前6内存情况%s.txt' % (self.get_time()[:10]), 'a')
            # g.write('%s\n' % (top6))
            # g.close()

    # 取日志,入参：str1，str2
    def logcat_pull(self, **msg):
        if not os.path.exists("tmp//logcat"):
            os.makedirs("tmp//logcat", exist_ok=True)
        try:
            self.shell('rm -r /data/local/tmp/logcat.txt')
            self.shell('logcat -v threadtime -d -f /data/local/tmp/logcat.txt')
            self.adb('pull /data/local/tmp/logcat.txt tmp//logcat//logcat%s-%s-%s.txt' % (
            self.get_time()[11:], msg['str1'], msg['str2']))
        except:
            self.print_before('取logcat失败')
            pass

    # 可疑情况截图并打开，入参：str1，str2自定义错误信息，截图后缀名
    def screenshot_err(self, **msg):
        try:
            icon_name = ('screenshot%s-%s-%s.jpg' % (self.get_time()[11:], msg['str1'], msg['str2']))
            self.screenshot(icon_name)
            os.system('start tmp/screenshot/%s' % (icon_name))
        except:
            self.print_before('screenshot_err失败')
            pass

    # 可疑情况截图不打开，入参：str1，str2自定义错误信息，截图后缀名
    def screenshot_err_no_open(self, **msg):
        try:
            icon_name = ('screenshot%s-%s-%s.jpg' % (self.get_time()[11:], msg['str1'], msg['str2']))
            self.screenshot(icon_name)
        except:
            self.print_before('screenshot_err_no_open失败')
            pass

    # 点亮解锁屏幕
    def screen_on(self):
        self.sendKeyEvent(keycode=224)
        if Element().info(resourceId='com.android.systemui:id/lock_icon'):
            self.swipeToUp()
    # 熄灭屏幕
    def screen_off(self):
        self.sendKeyEvent(keycode=223)
    # 判断屏幕是否点亮
    def is_screen_on(self):
        output = self.shell_return("dumpsys power")
        return 'mHoldingDisplaySuspendBlocker=true' in output

    def getH5PackageName(self):
        '''
        示例，暂时不用 。
        :return: 
        '''
        h5packageName = ''
        try:
            h5packageName = self.shell_return(
                'dumpsys activity activities | grep index')
            h5packageName = '/index'.join(h5packageName.split('/index')[:1])
            h5packageName = 'ULightApp/'.join(h5packageName.split('ULightApp/')[1:])
        except:
            pass
        if h5packageName == '':
            return ''
        else:
            return h5packageName

    # 获取ip地址
    def ipAddress(self):
        ipAddress0 = self.shell_return('ifconfig wlan0')
        ipAddress0 = 'ask'.join(ipAddress0.split('ask')[:1])
        if ipAddress0.count('ip'):
            ipAddress0 = 'ip'.join(ipAddress0.split('ip')[1:])
        elif ipAddress0.count('addr:'):
            ipAddress0 = 'addr:'.join(ipAddress0.split('addr:')[1:]).split(' ')[0]
        ip = ipAddress0.strip()
        try:
            ip = re.search('([\d]{1,3}\.){3}[\d]{1,3}', ip).group()
            if ip != '':
                return ip
        except:
            return ''
    # 获取物理网卡mac地址
    def get_mac(self):
        try:
            mac = self.shell_return('cat /sys/class/net/wlan0/address')
            mac = str(mac).replace('\r','').replace('\n','')
            if len(mac) < 21:
                return mac
        except:
            return ''
    # 获取指定设备已装包名版本信息
    def getVersionName(self,packageName):
        '''
        :param packageName: 包名
        :return: 内部版本号、版本名、首次安装时间、上次安装时间
        '''
        if packageName != '':
            versionName = self.shell_return(
                'dumpsys package %s | grep versionName' % (packageName)).replace(
                '\n', '').replace('\r', '').strip()
            versionCode = self.shell_return(
                'dumpsys package %s | grep versionCode' % (packageName)).replace(
                '\n', '').replace('\r', '')
            versionTime = self.shell_return(
                'dumpsys package %s | grep lastUpdateTime' % (packageName)).replace(
                '\n', '').replace('\r', '').strip()
            versionFirstTime = self.shell_return('dumpsys package %s | grep firstInstallTime' % (
            packageName)).replace('\n', '').replace('\r', '').strip()
            if versionCode != '':
                versionCode = versionCode.split(' ')
                i = 0
                versionCode_len = len(versionCode)
                while i < versionCode_len:
                    if versionCode[0] == '' or versionCode[0] == ' ':
                        versionCode.remove(versionCode[0])
                    else:
                        break
                    i += 1
                versionCode = versionCode[0]
            if versionTime != '':
                versionTime = versionTime.split('lastUpdateTime=')[1]
            if versionFirstTime != '':
                versionFirstTime = versionFirstTime.split('firstInstallTime=')[1]
            return [versionName, versionCode, versionFirstTime, versionTime]
    # 获取sn号
    def get_sn(self):
        serialno = self.shell_return('getprop persist.sys.product.serialno').replace(
            '\r', '').replace('\n', '')
        return serialno

    # 获取tusn号
    def get_tusn(self):
        tusn = self.shell_return('getprop persist.sys.product.tusn').replace(
            '\r', '').replace('\n', '')
        return tusn

    # python获取当前位置所在的行号和函数名
    def get_head_info(self):
        '''
        :return: D:/Python_script_selenium/adbUtil_test.py, texst, 10, 
        '''
        try:
            raise Exception
        except:
            f = sys.exc_info()[2].tb_frame.f_back
        return ' %s, %s, %s' % (f.f_code.co_filename, f.f_code.co_name, str(f.f_lineno))

    # 根据图片名判断当前页面
    def find_icon(self, icon_name, confidence = None):
        '''
        usage:  find_icon('icon/print_cancel.720x1280.jpg', '')
                find_icon('icon/print_cancel.720x1280.jpg', 0.9)
        :param icon_name: 本地图片路径，待查找的图
        :param confidence: 相似度
        :return: 位置坐标
        '''
        from androidtest import aircv as ac
        self.screenshot('screenshot.png')
        imsrc = ac.imread('tmp/screenshot/screenshot.png')  # 原始图像
        imsch = ac.imread(icon_name)  # 待查找的部分
        result = ac.find_template(imsrc, imsch)
        print(result)
        if not confidence:
            confidence = 0.95
        if result == None:
            return False
        elif result['confidence'] < confidence:
            return False
        else:
            location = result['result']
            return location

    # 点击找到的图片
    def find_icon_click(self, icon_name, confidence=None):
        '''
        usage:  find_icon_click('icon/print_cancel.720x1280.jpg', '')
                find_icon_click('icon/print_cancel.720x1280.jpg', 0.9)
        :param icon_name: 本地图片路径，待查找的图
        :param confidence: 相似度
        :return: True 或者 False
        '''
        location = self.find_icon(icon_name, confidence)
        if location:
            self.click(location[0], location[1])
            # print('点击位置：', location[0], location[1])
            return location
        else:
            print('未找到%s' % (icon_name))
            return False
    # 返回
    def back(self):
        self.sendKeyEvent(Keycode.BACK)
    # HOME键
    def home(self):
        self.sendKeyEvent(Keycode.HOME)
