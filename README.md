# uitest
基于adb的安卓自动化操作
使用：

导入包

import uitest

获得设备实例，入参（'12344321'）为序列号，一台设备可不填，作用是可以直接操作adb和shell命令

a = uitest.Device('12344321')

获得设备ui实例，可操作设备ui控件

d = uitest.connect('12344321')

获取当前包名

print(a.getCurrentPackageName())

获取剩余ram内存

print(a.getMemFree())

强行停止当前应用

a.force_stop(a.getCurrentPackageName())

获取第三方应用列表

print(a.getThirdAppList())

根据本地的图片来点击设备

print(a.find_icon_click('icon/screenshot.png'))

获取设备信息

print(d.device_info)

根据id来清除EditText输入框的内容

d(resourceId='com.test.lzz:id/user_name').clear_text()