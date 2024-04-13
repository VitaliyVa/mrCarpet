import { instance } from "./instance";

export const getProductsBySearchQuery = async (searchQuery) => {
  try {
    const { data } = await instance.get(
      `/products/?search_query=${searchQuery}`
    );

    return data;
  } catch ({ response }) {
    console.log(response);
  }
};
