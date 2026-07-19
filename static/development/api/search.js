import { instance } from "./instance";

export const getProductsBySearchQuery = async (searchQuery) => {
  try {
    const q = encodeURIComponent(String(searchQuery ?? "").trim());
    if (!q) return [];

    const { data } = await instance.get(`/products/?search_query=${q}`);
    const items = Array.isArray(data) ? data : data?.results || [];
    // Normalize image field: serializer uses image_url
    return items.map((item) => ({
      ...item,
      image: item.image || item.image_url || "",
    }));
  } catch ({ response }) {
    console.log(response);
    return [];
  }
};
