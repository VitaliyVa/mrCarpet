const path = require("path");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const OptimizeCssAssetsPlugin = require("optimize-css-assets-webpack-plugin");
const TerserPlugin = require("terser-webpack-plugin");
const isDev = process.env.NODE_ENV == "development";
const isProd = !isDev;

const optimization = () => {
  const config = {};
  if (isProd) {
    config.minimizer = [new TerserPlugin(), new OptimizeCssAssetsPlugin()];
  }
  return config;
};

const cssLoaders = (extra) => {
  const loader = [
    {
      loader: MiniCssExtractPlugin.loader,
      options: {
        hmr: isDev,
      },
    },
    "css-loader",
  ];

  if (extra) {
    loader.push(extra);
  }
  return loader;
};

module.exports = {
  context: path.resolve(__dirname, "development/pages"),
  entry: {
    index: "./index.js",
    favorite: "./favorite.js",
    catalog: "./catalog.js",
    catalog_inside: "./catalog_inside.js",
    basket: "./basket.js",
    product: "./product.js",
    blog: "./blog.js",
    blog_inside: "./blog_inside.js",
    about: "./about.js",
    success: "./success.js",
    delivery: "./delivery.js",
    policy: "./policy.js",
    refund: "./refund.js",
    terms: "./terms.js",
    faq: "./faq.js",
  },
  output: {
    filename: "[name]/index.js",
    path: path.resolve(__dirname, "source/pages/"),
  },
  resolve: {
    alias: {
      "@component": path.resolve(__dirname, "development/components"),
    },
  },
  devtool: isDev ? "source-map" : "",
  optimization: optimization(),
  devServer: {
    port: 3801,
    hot: isDev,
  },
  plugins: [
    new MiniCssExtractPlugin({
      filename: "[name]/index.css",
    }),
  ],
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        loader: {
          loader: "babel-loader",
          options: {
            presets: ["@babel/preset-env"],
          },
        },
      },
      {
        test: /\.css$/,
        use: cssLoaders(),
      },
      {
        test: /\.scss$/,
        use: cssLoaders("sass-loader"),
      },

      // {
      //     test: /\.(ttf|woff|woff2|eot)$/,
      //     use:['file-loader']
      // },
    ],
  },
};
