export const domainRegex = /^([a-zA-Z0-9\u4e00-\u9fa5]|[a-zA-Z0-9\u4e00-\u9fa5][-a-zA-Z0-9\u4e00-\u9fa5]*[a-zA-Z0-9\u4e00-\u9fa5])(\.([a-zA-Z0-9\u4e00-\u9fa5]|[a-zA-Z0-9\u4e00-\u9fa5][-a-zA-Z0-9\u4e00-\u9fa5]*[a-zA-Z0-9\u4e00-\u9fa5]))*(:\d+)?$/;

export function parseDomain(d) {
    let clean = d.trim();
    if (clean.indexOf("http://") === 0) clean = clean.substring(7);
    else if (clean.indexOf("https://") === 0) clean = clean.substring(8);
    if (clean.indexOf("/") !== -1) clean = clean.split("/")[0];
    
    // 处理带方括号的 IPv6 地址，例如 [2001:db8::1]:443 或 [2001:db8::1]
    if (clean.startsWith("[")) {
        const endBracket = clean.indexOf("]");
        if (endBracket !== -1) {
            const host = clean.substring(1, endBracket);
            let port = "443";
            const portPart = clean.substring(endBracket + 1);
            if (portPart.startsWith(":")) {
                const p = parseInt(portPart.substring(1));
                if (!isNaN(p)) {
                    port = p.toString();
                }
            }
            return { host, port };
        }
    }

    // 未加方括号的 IPv6 地址不包含端口；带端口必须使用 [地址]:端口。
    const colonCount = (clean.match(/:/g) || []).length;
    if (colonCount > 1) {
        return { host: clean, port: "443" };
    }

    // 普通域名/IPv4 且带端口，例如 example.com:8080 或 127.0.0.1:8080
    if (clean.indexOf(":") !== -1) {
        const parts = clean.split(":");
        return { host: parts[0], port: parts[1] || "443" };
    }

    return { host: clean, port: "443" };
}
