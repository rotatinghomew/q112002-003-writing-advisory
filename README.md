# 跨课程写作辅导资料

学期号是从 1 开始的顺序整数。目标组合以 `path` 命名；目标的一条先修路径中每个前项均要满足，命中其中一条路径即可。不同 `occasion` 才是隔次观察；同次讨论的不同形式不增加观察次数。`observation_map` 是两课写作组认可的观察对应关系。
`ruling` 对同一个观察编号在 `day` 上更新；`reject` 否定上次确认，`contested` 表示确认意见仍相冲，`accept` 表示通过。个人栏目为空时是一份小组说明；其中个人追认可通过确认记录标明。学期范围按目标表解释，超出时效的记录仍可回查。
辅导开放时段以业务日计，`verified` 是预计教师能完成确认的日子，不是练习举行的日期。跨课入学日来自注册数据。已约练习仍需人工确认，不能自动改约。

## 资料格式

资料是匿名合成登记，不包含真实学生、真实成绩或外部访问地址。UTF-8 JSON，每张表是对象数组；`null` 表示该字段无已知值。`records/catalog.json` 记录每张表的字段。

- `goals`：目标的独立要求、隔次次数和有效学期数。 字段：`goal`、`independent`、`occasions`、`valid_terms`。
- `prerequisites`：可替代路径与该路径的全部条件。 字段：`goal`、`path`、`required`。
- `observation_map`：课程允许的任务形式与对应目标。 字段：`activity`、`course`、`format`、`goal`、`term`。
- `observations`：group 与 student 为空分别表示无小组及未确认个人；support 指辅助条件。 字段：`observation`、`activity`、`student`、`group`、`occasion`、`term`、`support`、`day`。
- `rulings`：教师确认记录时间。 字段：`observation`、`student`、`state`、`day`。
- `admissions`：注册办公室给出的下一门课要求。 字段：`student`、`required`、`start_day`、`term`、`advisor`。
- `availability`：可参加辅导的日子。 字段：`student`、`day`。
- `workshops`：活动容量及可能提供的目标观察。 字段：`session`、`day`、`verified`、`seats`、`independent`、`covers`。
- `appointments`：已确认的预约，day 为确认日。 字段：`student`、`session`、`day`。

## 本地查看

使用 Python 3.11 标准库，无需安装包。用 `python3 record_reader.py` 检查并列出收到的表行数；也可传入同格式资料目录。用 `python3 -m unittest discover -v` 检查资料契约。读取入口不会计算分析结果。
