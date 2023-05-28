# ASMRManager
包含下载，管理，播放(命令行TUI)的 <https://asmr.one> 的 CLI管理工具。

## 功能介绍
### 下载
支持 关键词，标签索引，排序，过滤，目前只支持调用IDM下载，你也可以自己修改 spider.py 中的 download_file 方法。
```shell
> asmr dl search -h
2023-05-28 13:13:08 - INFO - Run program with: dl search -h
Usage: main.py dl search [OPTIONS] [TEXT]

  search and download ASMR by filters

Options:
  -t, --tags TEXT                 tags to include
  -v, --vas TEXT                  voice actor(cv) to include
  -c, --circle TEXT               circle(社团) to include
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
可以对作品进行评分，评论。也支持用关键词进行搜索(但需要一点sql基础，仓库提供了一些模板，见`sql.example/`)
### 播放
非常简陋的终端播放界面，支持歌词显示，自动切集，可以预见的将来应该会完善一下

## 使用方法
本工具支持 `python >= 3.10`, 安装方法如下：
```shell
git clone https://github.com/slqy123/ASMRManager.git
pip install -r .\requirements.txt
```
之后按照说明修改 `config.example.py` 文件，再将其重命名为 `config.py` 。
然后运行 `python main.py -h` 查看帮助说明。
也可以将本目录加入环境变量，然后运行 `asmr -h` 即可
## 其他
感谢 <https://asmr.one>丰富了我的夜生活。
另外网站运营不易，请合理使用本工具。