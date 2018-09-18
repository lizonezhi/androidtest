# androidtest
基于adb的安卓自动化操作
# 简介：项目依赖于uiautomator2, 由于有些场景下手机不支持安装apk， 所以参考@codeskyblue项目写了这个
安装：

pip install -U --pre uiautomator2

pip install -U --pre androidtest

导入包

import androidtest


获得设备实例，入参（'12344321'）为序列号，一台设备可不填，作用是可以直接操作adb和shell命令

adb = androidtest.Device('12344321')


获得设备ui实例，可操作设备ui控件

d = androidtest.connect('12344321')


获取当前包名

adb.getCurrentPackageName()


获取剩余ram内存

adb.getMemFree()


强行停止当前应用

adb.force_stop(adb.getCurrentPackageName())


获取第三方应用列表

adb.getThirdAppList()


根据本地的图片来点击设备

adb.find_icon_click('icon/screenshot.png')


获取设备信息

d.device_info


根据id来清除EditText输入框的内容

d(resourceId='com.test.lzz:id/user_name').clear_text()