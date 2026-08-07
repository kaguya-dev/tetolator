/* Thin fetch wrapper around the Tetolator REST API.
 * Every function returns a promise resolving to parsed JSON.
 * On HTTP errors the parsed {error: ...} message is thrown.
 */

const API = {
  async request(method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
      let msg = "Request failed";
      try {
        const data = await res.json();
        msg = data.error || msg;
      } catch (_) { /* keep default message */ }
      throw new Error(msg);
    }
    return res.json();
  },

  // clients
  listClients: () => API.request("GET", "/api/clients"),
  createClient: (data) => API.request("POST", "/api/clients", data),
  updateClient: (id, data) => API.request("PUT", `/api/clients/${id}`, data),
  deleteClient: (id) => API.request("DELETE", `/api/clients/${id}`),

  // filaments
  listFilaments: () => API.request("GET", "/api/filaments"),
  createFilament: (data) => API.request("POST", "/api/filaments", data),
  updateFilament: (id, data) => API.request("PUT", `/api/filaments/${id}`, data),
  deleteFilament: (id) => API.request("DELETE", `/api/filaments/${id}`),

  // prints
  listPrints: () => API.request("GET", "/api/prints"),
  createPrint: (data) => API.request("POST", "/api/prints", data),
  updatePrint: (id, data) => API.request("PUT", `/api/prints/${id}`, data),
  deletePrint: (id) => API.request("DELETE", `/api/prints/${id}`),
  previewCost: (data) => API.request("POST", "/api/prints/preview-cost", data),

  // settings
  getSettings: () => API.request("GET", "/api/settings"),
  updateSettings: (data) => API.request("PUT", "/api/settings", data),
};
