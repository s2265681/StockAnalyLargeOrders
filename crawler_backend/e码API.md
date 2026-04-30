

API说明
基础地址：http://api.eomsg.com/zc/data.php

编码：UTF-8

提交方式：GET

注意：
本平台API不需要查询项目或申请项目，可以直接取号使用。

API支持以下功能：
1.登录
2.查询余额
3.取号
4.取码
5.释放
6.拉黑
7.发送短信
8.查询历史记录

使用需注意的事项：
1.不通过API重新登录的话token不会失效
2.参数中的汉字或特殊符号需要URL编码。
登录[login]
调用实例：http://api.eomsg.com/zc/data.php?code=login&user=用户名&password=密码
成功返回值：token
失败返回值：ERROR:错误信息
错误信息举例：ERROR:验证未通过。如果您确定用户名和密码正确，请通过APP或网页版登录一次您的账号，通过APP或网页版登录成功后的6小时内，可继续调用当前登录API获取token
备注：为了账户安全，长时间不登录的用户和被系统判定有被盗号风险的用户，通过当前API获取新token时，需要先通过APP(或网页版)登录一次账号，API才能返回正确的token，否则返回错误信息（ERROE:错误信息）。使用登录API获取一次token后，token长期有效，不通过API重新登录的话token不会改变，如果通过API重新获取token则token会改变。在已有的token没有泄漏或被盗的情况下，不需要再次使用当前API获取新的token。
查询余额[leftAmount]
调用实例：http://api.eomsg.com/zc/data.php?code=leftAmount&token=登录获取的token
成功返回值：余额
失败返回值：ERROR:错误信息
备注：无
获取号码[getPhone]
调用实例：http://api.eomsg.com/zc/data.php?code=getPhone&token=登录获取的token&phone=130xxxxxxxx&province=宁夏&cardType=全部
参数：
phone：可选，指定的号码，不填的话表示随机获取号码；
province：可选，省份，具体名称可参照APP里的；
cardType：可选，选值范围：[实卡,虚卡,全部]。
成功返回值：手机号
失败返回值：ERROR:错误信息
备注：无
获取短信[getMsg]
调用实例：http://api.eomsg.com/zc/data.php?code=getMsg&token=登录获取的token&phone=165xxxxxxxx&keyWord=%E7%9F%A5%E4%B9%8E
参数：
phone：获取/指定的手机号，必填；
keyWord：短信关键词。设置不正确收不到短信，必填。
尚未收到返回值：如果包含“[尚未收到]”字样，说明尚未查询到短信。
成功返回值：短信内容
失败返回值：ERROR:错误信息
备注：短信关键词一般是短信黑括号里的名字，比如【毛竹】验证码9876，keyWord是“毛竹”二字。如果没有黑括号，可以使用短信里任意一个关键的字词。系统查询短信是查询包含这个词的短信，否则查不到。
释放号码[release]
调用实例：http://api.eomsg.com/zc/data.php?code=release&token=登录获取的token&phone=162xxxxxxxx
参数：
phone：获取/指定的手机号；
成功返回值：释放结果
失败返回值：ERROR:错误信息
备注：如果释放失败，跳过就行，无需一直重复释放。
拉黑号码[block]
调用实例：http://api.eomsg.com/zc/data.php?code=block&token=登录获取的token&phone=162xxxxxxxx
参数：
phone：获取/指定的手机号；
成功返回值：拉黑结果
失败返回值：ERROR:错误信息
备注：如果拉黑失败无需一直重复拉黑。
发送短信[send]
调用实例：http://api.eomsg.com/zc/data.php?code=send&token=登录获取的token&phone=162xxxxxxxx&toPhone=1069xxxxxxxx&content=xxxx
参数：
phone：获取/指定的手机号，用于发送短信；
toPhone：要发送到的号码；
projId：项目ID；
content：发送内容；
成功返回值：发送结果
失败返回值：ERROR:错误信息
备注：不能向个人手机号发送信息，发送垃圾信息会被封号。
查询历史记录[queryUsed]
说明：每分钟调用次数不能超过一次，否则系统会封禁账号的API调用。
调用实例：http://api.eomsg.com/zc/data.php?code=queryUsed&token=登录获取的token
参数：token：登录获取的token
成功返回值：历史记录，每条以换行符(\n)分割。
失败返回值：ERROR:错误信息
备注：返回最近24小时100条记录


