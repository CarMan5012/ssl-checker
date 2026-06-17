export const domainRegex = /^([a-zA-Z0-9]|[a-zA-Z0-9][-a-zA-Z0-9]*[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][-a-zA-Z0-9]*[a-zA-Z0-9]))*(:\d+)?$/;

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

    // 处理普通 IPv6 地址，包含多个冒号且无方括号
    const colonCount = (clean.match(/:/g) || []).length;
    if (colonCount > 1) {
        const lastColon = clean.lastIndexOf(":");
        const lastPart = clean.substring(lastColon + 1);
        if (/^\d+$/.test(lastPart)) {
            return { host: clean.substring(0, lastColon), port: lastPart };
        }
        return { host: clean, port: "443" };
    }

    // 普通域名/IPv4 且带端口，例如 example.com:8080 或 127.0.0.1:8080
    if (clean.indexOf(":") !== -1) {
        const parts = clean.split(":");
        return { host: parts[0], port: parts[1] || "443" };
    }

    return { host: clean, port: "443" };
}
