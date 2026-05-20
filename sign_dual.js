// sign_dual.js - 支持双网站的签到脚本
const fs = require('fs');
const path = require('path');
const cloudscraper = require('cloudscraper');

const LOG_DIR = path.join(__dirname, 'logs');
if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR);

// 网站配置
const SITES_CONFIG = {
  ns: {
    name: 'NodeSeek',
    domain: 'www.nodeseek.com',
    baseUrl: 'https://www.nodeseek.com',
    emoji: '🔵'
  },
  df: {
    name: 'DeepFlood',
    domain: 'www.deepflood.com', 
    baseUrl: 'https://www.deepflood.com',
    emoji: '🟢'
  }
};

function writeLog(message) {
  const filePath = path.join(LOG_DIR, `${new Date().toLocaleDateString('sv-SE')}.log`);
  const time = new Date().toLocaleString('zh-CN', { hour12: false });
  fs.appendFileSync(filePath, `[${time}] ${message}\n`);
}

function chunkString(str, length = 1000) {
  const chunks = [];
  for (let i = 0; i < str.length; i += length) {
    chunks.push(str.slice(i, i + length));
  }
  return chunks;
}

async function signSingle(name, cookie, siteType = 'ns', randomMode = false) {
  const siteConfig = SITES_CONFIG[siteType];
  if (!siteConfig) {
    const errorMsg = `❌ 不支持的网站类型: ${siteType}`;
    writeLog(errorMsg);
    return { name, result: errorMsg, time: new Date().toLocaleString(), site_type: siteType };
  }

  const url = `${siteConfig.baseUrl}/api/attendance?random=${randomMode ? 'true' : 'false'}`;
  const maskedCookie = cookie.length > 15
    ? cookie.slice(0, 8) + '...' + cookie.slice(-5)
    : cookie;

  const maxRetries = 3;
  let lastErrorResult = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    writeLog(`==== 开始签到: ${siteConfig.emoji} ${siteConfig.name} - ${name} (第 ${attempt} 次尝试) ====`);
    writeLog(`请求 URL: ${url}`);
    writeLog(`使用 Cookie(部分隐藏): ${maskedCookie}`);
    writeLog(`随机模式: ${randomMode}`);

    const headers = {
      'Accept': '*/*',
      'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
      'cookie': cookie,
      'Content-Length': '0',
      'Origin': siteConfig.baseUrl,
      'Referer': `${siteConfig.baseUrl}/board`,
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
    };

    try {
      const res = await cloudscraper.post({
        uri: url,
        headers,
        resolveWithFullResponse: true,
        body: '',
        simple: false,
        json: false,
      });

      const text = res.body;
      writeLog(`响应正文长度: ${text.length}`);

      // 优先尝试解析为 JSON
      let parsed;
      try {
        parsed = JSON.parse(text);
      } catch (e) {
        parsed = null;
      }

      if (parsed && typeof parsed === "object") {
        writeLog(`响应正文(JSON): ${text}`);
      } else {
        writeLog(`响应正文长度: ${text.length}`); 
        chunkString(text, 2000).forEach((chunk, i) => {
          writeLog(`响应正文第 ${i + 1} 段: （隐藏）`);
        });
      }

      try {
        const data = JSON.parse(text);
        const msgRaw = (data.message || '').toLowerCase();

        if (res.statusCode === 403) {
          const msg = `🚫 风控拦截`;
          writeLog(`${siteConfig.emoji} ${siteConfig.name} - ${name} 签到结果: ${msg}`);
          return { name, result: msg, time: new Date().toLocaleString(), site_type: siteType };
        }

        if (data.success) {
          const amountMatch = data.message.match(/(\d+)/);
          const amount = amountMatch ? amountMatch[1] : '未知';
          const msg = `✅ 签到收益 ${amount} 个 🍗`;
          writeLog(`${siteConfig.emoji} ${siteConfig.name} - ${name} 签到结果: ${msg}`);
          return { name, result: msg, time: new Date().toLocaleString(), site_type: siteType };
        } else if (msgRaw.includes('重复') || msgRaw.includes('already')) {
          const msg = `☑️ 已签到`;
          writeLog(`${siteConfig.emoji} ${siteConfig.name} - ${name} 签到结果: ${msg}`);
          return { name, result: msg, time: new Date().toLocaleString(), site_type: siteType };
        } else {
          const msg = `🚫 签到失败：${data.message || '未知错误'}`;
          writeLog(`${siteConfig.emoji} ${siteConfig.name} - ${name} 签到结果: ${msg}`);
          lastErrorResult = { name, result: msg, time: new Date().toLocaleString(), site_type: siteType };
        }
      } catch (jsonErr) {
        writeLog(`${siteConfig.emoji} ${siteConfig.name} - ${name} 响应解析异常:（隐藏）`);
        const msg = `🚫 响应解析失败，非 JSON 格式或登录失效`;
        writeLog(`${siteConfig.emoji} ${siteConfig.name} - ${name} 签到结果: ${msg}`);
        lastErrorResult = { name, result: msg, time: new Date().toLocaleString(), site_type: siteType };
      }
    } catch (err) {
      writeLog(`${siteConfig.emoji} ${siteConfig.name} - ${name} 请求异常: ${err.stack || err.message}`);
      const msg = `🚫 请求异常：${err.message}`;
      writeLog(`${siteConfig.emoji} ${siteConfig.name} - ${name} 签到结果: ${msg}`);
      lastErrorResult = { name, result: msg, time: new Date().toLocaleString(), site_type: siteType };
    }

    if (attempt < maxRetries) {
      await new Promise(res => setTimeout(res, 500));
    }
  }

  return lastErrorResult || { 
    name, 
    result: '🚫 未知错误', 
    time: new Date().toLocaleString(), 
    site_type: siteType 
  };
}

// 双网站签到函数
async function signAccounts(targets, userModes) {
  const results = {};
  
  for (const userId in targets) {
    results[userId] = {};
    const userSites = targets[userId];
    const userSiteModes = userModes[userId] || {};

    for (const siteType in userSites) {
      results[userId][siteType] = [];
      const accounts = userSites[siteType];
      const mode = userSiteModes[siteType] || false;

      for (const [name, cookie] of Object.entries(accounts)) {
        try {
          const res = await signSingle(name, cookie, siteType, mode);
          results[userId][siteType].push(res);
        } catch (e) {
          const siteConfig = SITES_CONFIG[siteType] || { emoji: '❓', name: 'Unknown' };
          results[userId][siteType].push({
            name,
            result: `🚫 签到异常: ${e.message}`,
            time: new Date().toLocaleString(),
            site_type: siteType
          });
          writeLog(`⚠️ 用户 ${userId} ${siteConfig.emoji} ${siteConfig.name} 账号 ${name} 签到异常: ${e.stack || e.message}`);
        }
      }
    }
  }
  
  return results;
}

module.exports = { signSingle, signAccounts };

// CLI 入口：供 Python 调用
if (require.main === module) {
  (async () => {
    try {
      const payload = JSON.parse(process.argv[2]);
      const { targets, userModes } = payload;
      const results = await signAccounts(targets, userModes);
      console.log(JSON.stringify(results));
    } catch (err) {
      console.error("sign_dual.js 运行出错:", err.message);
      process.exit(1);
    }
  })();
}