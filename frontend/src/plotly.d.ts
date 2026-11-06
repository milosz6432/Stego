declare module "plotly.js-dist-min" {
  const Plotly: {
    react: (el: HTMLElement, data: any[], layout?: any, config?: any) => Promise<any>;
    newPlot: (el: HTMLElement, data: any[], layout?: any, config?: any) => Promise<any>;
    purge: (el: HTMLElement) => void;
    [key: string]: any;
  };
  export default Plotly;
}
