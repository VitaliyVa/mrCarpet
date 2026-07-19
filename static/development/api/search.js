import { instance } from "./instance";

export const getProductsBySearchQuery = async (searchQuery) => {
  try {
    const q = encodeURIComponent(String(searchQuery ?? "").trim());
    if (!q) return [];

    const { data } = await instance.get(`/products/?search_query=${q}`);
    return Array.isArray(data) ? data : data?.results || [];
  } catch ({ response }) {
    console.log(response);
    return [];
  }
};
