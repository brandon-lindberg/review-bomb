import tailwindcssPostcss from "./frontend/node_modules/@tailwindcss/postcss/dist/index.mjs";

const config = {
  plugins: [tailwindcssPostcss()],
};

export default config;
