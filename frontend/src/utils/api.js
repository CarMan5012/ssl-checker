export async function apiFetch(url, options = {}, onUnauthorized) {
    try {
        const res = await fetch(url, options);
        if (res.status === 401) {
            if (onUnauthorized) {
                onUnauthorized();
            }
            throw new Error("Unauthorized");
        }
        return res;
    } catch (e) {
        if (e.message !== "Unauthorized") {
            throw e;
        }
        return null;
    }
}
