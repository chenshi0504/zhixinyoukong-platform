# API接口说明文档

## 文件说明

本目录包含智信优控综合交通实验平台的API接口说明文档。

## 文件列表

API接口说明文档.md：Markdown格式的API文档（源文件）

API接口说明文档.docx：Word格式的API文档（生成文件）

convert_to_docx.py：Markdown转DOCX的Python脚本

生成DOCX文档.bat：Windows批处理文件，一键生成DOCX

README.md：本说明文件

## 使用方法

### 方式一：使用批处理文件（推荐）

双击运行生成DOCX文档.bat

脚本会自动检查Python环境和依赖

自动生成API接口说明文档.docx

### 方式二：手动运行Python脚本

安装依赖：pip install python-docx

运行转换脚本：python convert_to_docx.py

## 环境要求

Python 3.7+

python-docx库

## 文档内容

API接口说明文档包含以下内容：

1. 概述：平台定位、API设计理念、技术栈

2. 接口架构设计：系统整体架构、API模块划分、版本管理

3. 认证与授权：JWT认证流程、Token格式、权限控制

4. 通用规范：请求规范、响应规范、HTTP状态码、分页规范

5. 核心接口模块：8个主要模块的接口说明
   认证模块
   用户管理模块
   数据采集模块
   交通流模块
   控制策略模块
   仿真场景模块
   实验任务模块
   实验报告模块

6. 错误处理：错误响应格式、常见错误码、错误处理建议

7. 调用示例：JavaScript、Python、cURL调用示例

8. 扩展指南：新模块开发规范、版本升级策略、性能优化、安全性建议、文档维护

## 更新文档

如需更新文档内容：

编辑API接口说明文档.md

运行生成DOCX文档.bat重新生成DOCX文件

## 注意事项

Markdown文件是源文件，所有修改应在此文件中进行

DOCX文件是生成文件，每次运行脚本会覆盖

转换脚本支持标题、表格、代码块等Markdown格式

## 技术支持

如有问题，请联系开发团队。

---

更新时间：2024年11月18日
