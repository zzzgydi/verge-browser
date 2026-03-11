这个项目，目标是让用户可以自己部署，然后有简单的鉴权逻辑。用户可以部署的时候可以配置admin auth token。

其中，还需要有一个管理页面，可以让用户自己管理自己的实例情况。这里我倾向于使用vite + react的组合。这里用户用admin auth token登录后，就可以看到自己所有的实例情况。

另一个最主要的目的是可以给agent方便使用，这样就意味着鉴权之类的逻辑要高度封装。
所以需要有一个SDK，包装为给agent友好的cli，可以进一步包装为skills，从而方便导入和使用。

人用这个项目，最主要的目的是可以用vnc配合agent来使用，有一些东西非要用户自己来操作的时候，可以自己操作，比如扫码登录，账号登录等。

而agent用这个项目，是可以结合playwright来使用，从而可以非常方便的进行自动化操作。这个可以参考 https://github.com/vercel-labs/agent-browser 这个项目。

- agent-browser 更偏 agent-first 没错，但是我们这个项目也要偏向 agent first，agent-browser有的，我们给agent侧使用的时候也要有
- 假设我们已经做好了这样一个verge-browser cli，那么我觉得他应该先访问env里的VERGE_BROWSER_TOKEN，作为admin的token。然后如果请求时不带 token ，应该报401，不应该默认为 anonymous。其次鉴权这个做小，不用做成什么产品能力
- 每个sandbox可以添加alias，这样用户可以通过别名来区分和获取浏览器信息，然后cli的名称就叫verge-browser，不许叫verge
- 业务api如果没有token，都要报401，不允许匿名
- 永远不做多用户账号系统，也不支持多角色权限模型
