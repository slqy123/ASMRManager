# ASMRSpider

![](https://img.shields.io/badge/python-%3E=3.9-green.svg)

一个简单的 <https://asmr.one> 爬虫。

## 怎么用

clone 项目, 编辑 [app/config.py](https://github.com/DiheChen/ASMRSpider/blob/master/app/config.py), 填入你在 <https://asmr.one> 注册的账号和密码, 如果不修改, 则用游客账户登录。

```bash
python -m pip install -U pip

python -m pip install -r requirements.txt
```

开始使用:

```bash
python main.py RJ373001 RJ385913
# 如果还有更多要下载的音声, 加在后面就行
```

由于 Python 版部署较麻烦, 此分支将归档, 建议看 [这个分支](https://github.com/DiheChen/go-asmr-spider/tree/master)。

## 致谢

感谢 <https://asmr.one>, 现在每天都有不同的女孩子陪我睡觉。

```json
{
  "order": [
    "create_date",
    "rating",
    "release",
    "dl_count",
    "price",
    "rate_average_2dp",
    "review_count",
    "id",
    "nsfw",
    "random"
  ],
  "sort": ["asc", "desc"]
}
```