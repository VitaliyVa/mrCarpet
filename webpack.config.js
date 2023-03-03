const path = require("path");
const HtmlWebpackPlugin = require("html-webpack-plugin");
const CopyWebpackPlugin = require("copy-webpack-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const ImageminPlugin = require("imagemin-webpack-plugin").default;

module.exports = {
  entry: {
    index: "./src/pages/index/index.ts",
    about: "./src/pages/about/index.ts",
    contact: "./src/pages/contact/index.ts",
  },
  output: {
    path: path.resolve(__dirname, "dist"),
    filename: "[name]/index.js",
    publicPath: "",
  },
  module: {
    rules: [
      {
        test: /\.tsx?$/,
        use: "ts-loader",
        exclude: /node_modules/,
      },
      {
        test: /\.scss$/,
        use: [MiniCssExtractPlugin.loader, "css-loader", "sass-loader"],
        include: path.resolve(__dirname, "src/pages"),
      },
      {
        test: /\.(png|jpe?g|gif)$/i,
        use: [
          {
            loader: "file-loader",
            options: {
              name: "[name].[ext]",
              outputPath: "images",
            },
          },
        ],
      },
    ],
  },
  resolve: {
    extensions: [".tsx", ".ts", ".js"],
  },
  plugins: [
   
    new HtmlWebpackPlugin({
      template: "./src/pages/index/index.html",
      filename: "index.html",
      chunks: ["index"],
      inject: "body",
      // Добавить свойство для указания корректного пути к CSS файлу
      // в зависимости от имени страницы
      templateParameters: {
        pageCss: "index/index.css",
      },
    }),
    new HtmlWebpackPlugin({
      template: "./src/pages/about/about.html",
      filename: "about.html",
      chunks: ["about"],
      inject: "body",
      templateParameters: {
        pageCss: "about/about.css",
      },
    }),
    new HtmlWebpackPlugin({
      template: "./src/pages/contact/contact.html",
      filename: "contact.html",
      chunks: ["contact"],
      inject: "body",
      templateParameters: {
        pageCss: "contact/contact.css",
      },
    }),
    new MiniCssExtractPlugin({
      filename: "[name]/[name].css",
    }),
    new CopyWebpackPlugin({
      patterns: [
        { from: "src/images/**/*", to: "images/[name].[ext]" },
        { from: "src/pages/**/*.scss", to: "[name]/[name].css" },
        { from: "src/styles/**/*.scss", to: "[path][name].css" },
      ],
    }),
    new ImageminPlugin({
      test: /\.(jpe?g|png|gif|svg)$/i,
      cacheFolder: path.resolve(__dirname, 'cache'),
      disable: process.env.NODE_ENV !== 'production',
      pngquant: {
        quality: '30'
      },
      jpegtran: {
        progressive: true
      },
      svgo: null,
      gifsicle: null
    })
  ],
};
