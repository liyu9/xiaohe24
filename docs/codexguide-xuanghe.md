# 爆肝两周,我把 Codex 最全实战指南开源了

**作者:** 苍何
**来源:** 微信公众号「苍何」
**日期:** 2026-05-27
**原文:** https://mp.weixin.qq.com/s/kJYmszZc9w2UoZBZ5EfDNQ

---

> **摘要:** 作者(苍何)爆肝两周把 Codex 实战指南开源到 GitHub, 内容覆盖 Codex 桌面 App、CLI、ChatGPT 入口、IDE 插件、订阅充值教程、配置指南,以及 Codex × Draw.io MCP 画架构图、Codex × GitHub Actions 自动修 CI、Codex × Obsidian 搭 AI 知识库等 13 个实战案例。

---

这是苍何的第 538 篇原创！

大家好，我是苍何。

今天，我们正式推出 **CodexGuide。**

这是一份《Codex 实战指南》，并已经在 GitHub 上开源。
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaAL7wkZJ6BVbib5ia1LFxHRN6ahEgM5xDaXDPRNjeNic90dbyibQcKKlsXKyd5N2nUQcZOsnicPK1GsoJnCbP0jBIicAmqc2pkFibgaib8/640?from=appmsg)

它是完全免费的、开源的。
![image](https://mmbiz.qpic.cn/mmbiz_png/zw8bZHsVSaBBsCHxtSoSAC7SBe9pZqGT6W1UAKpFKicOMBjn62cEThicgGLwcD8SGaLQia37nPopvyMG4uw3bqUiatGkico2Jp1YBc7pR1rhjvSU/640?from=appmsg)

为了更好的阅读，我还搭了个**在线网站**：
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaAH3GicmX5q8ee0AfzqjwKOzokUThGzrYd5FMjEnhn4jicAo1WmMALkLhJk9CfgXcqqpIkawD9CnfqKOASvAhMh55A0ibhTM7Nvyk/640?from=appmsg)

今天，正式宣发了：
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaBhHX4ec95SnCBhdRnGwWAAjOvicicd9huIo08EC3UiaKFOyAgXFTW5qVmtDCcWUDs7MdafZp22093HOhUODYdib5D1icJB1sYicPOLg/640?wx_fmt=png&from=appmsg)

我相信很多人和之前的我一样，对 Codex APP、Codex Cli 以及 Codex 插件会有点懵。

一会儿说用 Claude Code，一会儿说用 Codex，人会变得晕头转向。

所以，从学习路线开始，CodexGuide 按“认识入口、跑通任务、建立方法、团队沉淀”四层组织。你可以从 CLI 入门，也可以从桌面端、ChatGPT 或云端任务开始；关键在于先理解每个入口适合承载的任务节奏。
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaCPgntibicEqicOoWWtFib63urLfVYGNMZaBvzXD6uUtEicoaVct02LkpXEkdoyupHxJySBCBpagJep5Q5K0mOQHq7JOLvqoN9Yu9cU/640?from=appmsg)

现阶段大家用的最多的是 Codex 的桌面端 APP，他的工程化能力非常好，特别是 computer use 和浏览器能力。

从 Codex 桌面 App 下载与安装到订阅 Plus，CodexGuide 都非常细致的做了教程。
![image](https://mmbiz.qpic.cn/mmbiz_png/zw8bZHsVSaCrjOYibHP1RWiaicr5HKVuYXkKO7AeAGNqt4JA7AHY66xeFWVfNp1oNxibcTznicticCLoYO4mNNibCN9ZKk6oI6aYibWr47tg1iciajcds/640?from=appmsg)

光订阅 Plus 这个教程，说实话，就能帮你省不少找人代充的钱，哈哈。
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaDraicvxFBClcFLcU7tlWx2R3RS2QqIUKbgybFuVCLHAEoEaRsS82RDFFGXjvicB7IsnJPjUxnhanoJhWzb6Suvwm4o9Vdyv3WAE/640?from=appmsg)

自己的号充值会更加稳定些，毕竟那是属于你自己的号：
![image](https://mmbiz.qpic.cn/mmbiz_jpg/zw8bZHsVSaCqsxo3DK8KbbS5O5sVicfGNBuGDiciaMEpFucoYWJHxV32nrSwegZLPHMgPhbI34WzjTeTibkqDP2BteUPf4walbnP0kIEaZaee98/640?from=appmsg)

以及如何用手机端 Codex 来远程执行任务，我也基于亲身实践放了教程。

> 

这里说的“手机端 Codex”，更准确地说，是 ChatGPT 手机 App 里的 Codex 入口。它不是单独的手机 Codex App，也不是把手机变成远程桌面鼠标键盘。你可以把它理解成：桌面 App、远程开发机或其他已授权环境里正在运行 Codex，手机端负责连接这些环境，让你在离开电脑时继续查看、回复、审批和调整任务。

![image](https://mmbiz.qpic.cn/mmbiz_png/zw8bZHsVSaAYfszyUQY7gr2pNl0wxXAOaNIj8sK9nsC6ZUB59qiaeFnTfRkU3lW63ucCJwtJ38qhdjUkTKNQFgh6coIMmIYU6xLrJHLVoYlY/640?from=appmsg)

我现在几乎除了睡觉，都能随时 vibe coding 了，用手机在哪里都很方便指挥我的 mac mini 上的 Codex 来工作。
![image](https://mmbiz.qpic.cn/mmbiz_jpg/zw8bZHsVSaDVuYTOhiaOjyicz5KctY52src4fQofndIVXCZompdncRzjf5TFVCYooIGmJq9223nSDnia0EBJG1psBEnjqF2AtnsPFhciaicKLUNI/640?from=appmsg)

> 

后面，我也会把我的更多 Codex 实践放上来。

在入口地图中会介绍不同端侧的入口，从 cli 到桌面 APP，再到 IDE，带你一次性了解 Codex。
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaCNJpDtTrdLp6AWibiaIVTvWKQHjNMcYgkw8niaBWwRDL3UMO99OJ6nJSJ1PgROiafEoxICz61mZKKroWUWV0XpETzojLIhsTbMicQY/640?from=appmsg)

如果你对 Codex 的配置感到痛苦，也没关系，你都能找到答案。
![image](https://mmbiz.qpic.cn/mmbiz_png/zw8bZHsVSaBS5T5zZOZNBlicmeK5n9ZrhIpBmj3fGJalccCZl27XpKrwOtOsNhUcRIm3lRHG8XMRkYq3agNQDmyiaqfnhZ6uPUq8SiccyxJlibI/640?from=appmsg)

我还特意加了资源入口，方便大家第一时间找到官方的资料做索引，不过我会让 Codex 定时的检查，保证文档的更新和官方是同步的，至少不会延迟太多。

毕竟现在 Codex 的更新速度，非常非常快。
![image](https://mmbiz.qpic.cn/mmbiz_png/zw8bZHsVSaA8zvFgcVnGfsNIrk7DjbITVyib1u6OWQw9gXBBicK9HA2KMrrZXvwEg0qQ5uJ1oMB7QFeBG7dYcIibicFSuM9hxrrayGEtJcDiaaQY/640?from=appmsg)

单纯的教程只能是简单的入门，我还提议加了一个专栏，就是「实战案例」
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaCusXMRWBzUch9lW2Xicd02FmL3byp5O2icUlt6xYdfcicibibzYcky3M6p62xwoNKfdq1K2FD8dHtCnGm9tnHvDySIpKHoT58EtDEQ/640?from=appmsg)

会搜集比较多的 Codex 有意思的案例，主打一个有手就行，轻松复刻。

就比如用 Codex × Draw. io MCP 让AI 自动绘制架构图。
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaD0yh4ql9BWia2OeZibXSqttSh71VZLsqqvIkqOey8KFJ8Oxh3RUBo6c9EFt3JiafuFiadnhgCnpWXDdWFOicTjVFWlmo5EWr6uia2R8/640?from=appmsg)

这样有用的 case，没有宝子会拒绝吧。
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaD2vk1kianP2r1dVhV3yZ8diaS8Kdr8fmHibkYkR1H2xWLrqb0iaRholEVVCnNa6RH2UddBiaZzdudgUjHnaorYVGlhMLT9dmn6VNvM/640?from=appmsg)

不过，我们现在仅仅搜集了 13 个典型的案例，更多的实用案例，也会在之后不断完善搜集。

像 Codex × GitHub Actions：CI 失败自动修复实测，这样对于开发场景类的还是非常推荐大家上手试一试的。让自己的 Codex 起飞的一 part。
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaB5XiamgvRpzrSpfQGaeibGv79gI0OXhuPX3Fy7ZxA2HC7eIprDwwVxveO0K44CcfU2jTFjP3eCMFPP6Qgt5fygYPe3C1vTUlKW8/640?from=appmsg)

如果你比较喜欢知识管理，那你一定不要错过 Codex+ Obsidian 这个案例，他教你用 Codex × LLM Wiki，在 Obsidian 中搭建 AI 知识库。
![image](https://mmbiz.qpic.cn/sz_mmbiz_png/zw8bZHsVSaBlLibg4EAibmjSh2lQMRDmzrVeZwRNVMicN7VgoWbrdI0V1tYRMfytMrKliaWDg8libm3lPTQRsYgLatj1Lf82LoDrs5ZfaZcibKiank/640?from=appmsg)

说实话，这个项目 5 月 1 号就开始搞了，断断续续在完善。

起因很简单，我当时连 Codex 的登录和充值都搞不定，问了一圈 AI，翻了一圈教程，全是废话。

最后靠自己瞎试，才摸出来一条路。

那一刻我就悟了：Codex 这东西，难的不是用，是「用上」。

很多人不是不想用，是卡在账号、环境、网络这些破事上，直接劝退了。

官方文档倒是有，但你懂的，那玩意儿是写给已经会的人看的。

所以我就想，干脆自己整一份，从注册到实战，把坑全踩一遍，再铺平了给后面的人走。

还有个私心，我最近用 Codex 属于上瘾状态，天天跟它对线，踩的坑比写的代码还多。

与其让这些经验烂在聊天记录里，不如沉淀下来，也算给自己一个交代。

如果这份教程能让你少走哪怕一个弯路，那我这两周的黑眼圈就没白长。

最后感谢参与本开源教程共建的各位小伙伴，也欢迎社区共建，一起打磨。

虽然他还是不完美的，但完成比完美重要。

感谢你喜欢我的文章，我们下一期见啦。
