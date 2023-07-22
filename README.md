# ASMRManager

包含下载，管理，播放(命令行 TUI)的 <https://asmr.one> 的 CLI 管理工具。

## 功能介绍

### 下载

支持网站所支持的所有索引方式(关键词，tag，circle，价格，声优，日期等等)，以及排序方式。
目前只支持调用 IDM 下载，你也可以自己修改 spider.py 中的 `download_file` 方法。

```shell
> asmr dl search -h
2023-07-17 01:52:02 - INFO - Run program with: dl search -h
Usage: main.py dl search [OPTIONS] [TEXT]

  search and download ASMR by filters

  the [multiple] options means you can add multiple same option such as:

      --tags tag1 --tags tag2 --no-tags tag3

  for options like --rate, --sell, --price, you should give a interval like:

      --rate 3.9:4.7 --sell 1000: --price :200

  the interval a:b means a <= x < b, if a or b is not given i.e. a: or :b, it
  means no lower or upper limit

Options:
  -t, --tags TEXT                 tags to include[multiple]
  -nt, --no-tags TEXT             tags to exclude[multiple]
  -v, --vas TEXT                  voice actor(cv) to include[multiple]
  -nv, --no-vas TEXT              voice actor(cv) to exclude[multiple]
  -c, --circle TEXT               circle(社团) to include
  -nc, --no-circle TEXT           circle(社团) to exclude[multiple]
  -r, --rate TEXT                 rating interval
  -s, --sell TEXT                 selling interval
  -pr, --price TEXT               pirce interval
  -p, --page INTEGER              page of the search result  [default: 1]
  -s, --subtitle / -ns, --no-subtitle
                                  if the ASMR has subtitle(中文字幕)  [default:
                                  no-subtitle]
  -o, --order [create_date|rating|release|dl_count|price|rate_average_2dp|review_count|id|nsfw|random]
                                  ordering of the search result  [default:
                                  release]
  --asc / --desc                  ascending or descending
  -h, --help                      Show this message and exit.
```

### 管理

可以对作品进行评分，评论。也支持用关键词进行搜索(但需要一点 sql 基础，仓库提供了一些模板，例如 [search.sql](./sqls.example/search.sql))

### 播放

非常简陋的终端播放界面，支持歌词显示，按照歌词信息快进，切换歌曲，可以预见的将来应该会完善一下

## 使用方法

本工具支持 `python >= 3.10`, 安装方法如下：

```shell
git clone https://github.com/slqy123/ASMRManager.git
cd ASMRManager
pip install -e .
```

之后按照说明修改 `config.example.py` 文件，再将其重命名为 `config.py` 。
如果需要使用`sql`命令的话，请自行定制 `sqls.example` 目录下的 sql 文件，若有不明白的地方可使用 sqlite 数据库工具查看目录下的 data.db 文件，再将文件夹重命名为 `sqls` 。
完成后使用 `asmr -h` 查看各命令的使用说明，对于子命令不清楚的同样可以查看帮助，例如 `asmr dl -h`。

## 其他

感谢 <https://asmr.one>丰富了我的夜生活。
另外网站运营不易，请合理使用本工具。

2023-07-22 用做 download_path 的硬盘正式宣布寿终正寝，好吧这也是我为什么要设 download_path 和 storage_path 的原因，想最大限度地利用一下这快年老色衰的硬盘。
