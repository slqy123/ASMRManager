# ASMRManager

包含下载，管理，播放(命令行 TUI)的 <https://asmr.one> 的 CLI 管理工具。

## 功能介绍

### 下载

支持网站所支持的所有索引方式(关键词，tag，circle，价格，声优，日期等等)，以及排序方式。
目前仅支持调用 IDM 或 aria2 下载。

```
> asmr dl search -h
2023-09-30 15:52:08 - INFO - Run program with: dl search -h
Usage: asmr dl search [OPTIONS] [TEXT]

  search and download ASMR

  the [multiple] options means you can add multiple same option such as:

      --tags tag1 --tags tag2 --no-tags tag3

  for options like --rate, --sell, --price, you should give a interval like:

      --rate 3.9:4.7 --sell 1000: --price :200

  the interval a:b means a <= x < b, if a or b is not given i.e. a: or :b, it
  means no lower or upper limit

  --force will check the download RJ files again though it is already  in the
  database, it work just like update

  --replace option will first delte the original file, then add the new file
  to download queue(i.e. IDM or aria2)

  nsfw will only show the full age ASMRs

  for other --order values, you can refer to the website for explicit meaning

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
  --all / --select                download all RJs  [default: select]
  -p, --page INTEGER              page of the search result  [default: 1]
  --subtitle / --no-subtitle      if the ASMR has subtitle(中文字幕)  [default:
                                  no-subtitle]
  -o, --order [create_date|rating|release|dl_count|price|rate_average_2dp|review_count|id|nsfw|random]
                                  ordering of the search result  [default:
                                  release]
  --asc / --desc                  ascending or descending
  --force / --check-db            force download even if the RJ id exists in
                                  database,or by default, RJ already in the
                                  database will be skipped
  --replace / --no-replace        replace the file if it exists  [default: no-
                                  replace]
  --filter / --no-filter          filter out the files to download, rules are
                                  in the config file  [default: filter]
  -h, --help                      Show this message and exit.
```

### 管理

可以对作品进行评分，评论。也支持用关键词进行搜索(但需要一点 sql 基础，仓库提供了一些模板，例如 [search.sql](./asmrmanager/filemanager/resources/sqls.example/search.sql))

### 播放

非常简陋的终端播放界面，支持歌词显示，按照歌词信息快进，切换歌曲，支持以pygame(sdl)或mpd做为后端，可以预见的将来应该会完善一下(但感觉够用了应该不会再加啥功能了)。
![tui-screenshot](./assets/tui-screenshot.png)

## 使用方法

本工具支持 `python >= 3.10`, 安装方法如下：

```shell
pip install ASMRManager[依赖]
```

可选则的依赖项有 `idm`, `aria2`, `tui`，`pygame`,`mpd`, `all`，多个依赖使用逗号分隔，其中`all`为安装所有依赖。例如 `pip install ASMRManager[idm,tui]`

- 下载：`idm` 或 `aria2` 二选一，`idm` 为 windows 平台专用，`aria2` 为跨平台。
- 播放：`pygame` 或 `mpd` 二选一。
- 其他：`tui` 为可视化命令行界面。

> 此处也可以选择使用 `pipx` 来替代 `pip`，避免污染全局环境。
> 安装方法：`pip install pipx`

---

之后再运行 `asmr` 命令，会生成示例的配置文件和 sql 文件，此处以 windows 举例：

```
2023-10-22 14:36:21 - INFO - First time to run, copy default sqls to C:\Users\slqy\AppData\Local\asmrmanager\asmrmanager\sqls
2023-10-22 14:36:21 - INFO - An example config file has been copied to C:\Users\slqy\AppData\Local\asmrmanager\asmrmanager\config.toml, please modify it and run this command again
```

之后按照说明修改 `config.toml` 文件，如果使用 sql 的话，也可以对 sql 文件夹进行修改。

若有不明白的地方可使用 sqlite 数据库工具查看目录下的 data.db 文件。

完成后使用 `asmr -h` 查看各命令的使用说明，对于子命令不清楚的同样可以查看帮助，例如 `asmr dl -h`。
常用的命令有：
- `dl search` 搜索并下载。
- `info` 搜索某个 RJID 的具体信息
- `view` 将选择文件并移动到 VIEW_PATH
- `review` 为某个作品评分并评论(本地)
- `pl add` 将某个音声添加到用户的云端播放列表(配合 `pl create` 使用)

> 使用命令时，如果不输入 RJID ，将会自动使用上一次命令的RJID。

另外本工具提供基于 `trogon` 的可视化命令行界面，在安装`tui`依赖后使用 `asmr tui` 即可打开。

## 关于`dl search/get`的使用
命令执行过程中会进行如下的检查与过滤操作：
1. 开始下载前：检查RJ号是否应该下载，如果本地文件不存在或者数据库无记录都会执行下载操作。可以通过 `--force` 强制执行下载。
1. 获取音声信息后：检查音声的tags，如果包含tag_filters里指定的tag，则跳过下载。可以通过 `--ignore-tag` 来强制下载。
1. 获取下载文件后：检查文件的名称和路径，如果不符合filename_filters里指定的规则，则跳过下载。可以通过`ignore-name`来强制下载。
1. 添加下载任务时：如果检测到本地有同名文件，则跳过该文件的下载。可以通过`--replace`来强制覆盖存在的文件。

## 其他

感谢 <https://asmr.one>丰富了我的夜生活。
另外网站运营不易，请合理使用本工具。
