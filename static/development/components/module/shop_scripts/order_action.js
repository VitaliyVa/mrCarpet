function nova_pochta() {

    let select_city, select_department;

    create_city_select({
        city_name: ".select_city",
        select_noResult: "Міст не знайдено",
        api: "/api/settlements/"
    })

    create_department_select({
        city_name: ".select_city",
        department_name: ".select_department",
        select_noResult: "Відділень не знайдено",
        api: "/api/warehouses/"
    })




    function create_city_select({ city_name, select_noResult, api }) {
        select_city = new TomSelect('.select_city', {
            create: false,
            maxOptions: 100,
            valueField: 'value',
            labelField: 'title',
            searchField: 'title',
            sortField: {
                field: "text",
                direction: "asc"
            }
        });


        fetch(api, {
            method: 'GET',
        })
            .then(data => {
                return data.json();
            })
            .then(data => {
                data.results.forEach(element => {
                    select_city.addOption({
                        value: element.title,
                        title: `${element.title} (${element.region.title})`,
                    });
                });
                select_city.setValue([data.results[0].title]);
            });



        // let select_city = $(city_name).select2({
        //     dropdownAutoWidth: true,
        //     width: "resolve",

        //     language: {
        //         noResults: function () {
        //             return gettext(select_noResult);
        //         },
        //     },
        //     ajax: {
        //         url: api,
        //         data: function (params) {
        //             var query = {
        //                 per_page: 20,
        //                 title: params.term,
        //                 page_number: params.page || 1,
        //             };

        //             return query;
        //         },
        //         processResults: function (data, params, ...props) {
        //             params.page = params.page || 1;

        //             let options = data.results.map((item) => {
        //                 let result;
        //                 if (item.region.title != '') {
        //                     result = `${item.title} (${item.region.title})`;
        //                 } else {
        //                     result = `${item.title}`;
        //                 }
        //                 return {
        //                     id: item.id,
        //                     text: result,
        //                     item,
        //                 };
        //             });

        //             return {
        //                 results: options,
        //                 pagination: {
        //                     more: params.page * 30 < data.count,
        //                 },
        //             };
        //         },
        //     },
        // });

        return select_city;
    }



    function create_department_select({ city_name, department_name, select_noResult, api }) {

        select_department = new TomSelect('.select_department', {
            create: false,
            valueField: 'value',
            labelField: 'title',
            searchField: 'title',
            sortField: {
                field: "text",
                direction: "asc"
            },
            render: {
                no_results: function (data, escape) {
                    return '<div class="no-results">Цього відділення не існує або в обраному місті немає відділень нової почти</div>';
                },
            }
        });
        select_city.on('change', function (item) {
            fetch(`${api}?query=${item}`, {
                method: 'GET',
            })
                .then(data => {
                    return data.json();
                })
                .then(data => {
                    let length = data.results.length;
                    console.log('length: ', length);
                    select_department.clear();
                    select_department.clearOptions();
                    if (length >= 1) {
                        let first_value = data.results[0].title;

                        data.results.forEach(element => {
                            select_department.addOption({
                                value: `${element.title}`,
                                title: `${element.title}`,
                            });
                        });
                        select_department.setValue([first_value]);
                    } else {

                    }


                });
        });




        // $(department_name).select2({
        //     dropdownAutoWidth: true,
        //     width: "resolve",
        //     language: {
        //         noResults: function () {
        //             return select_noResult;
        //         },
        //     },
        // });

        // $(city_name).on("select2:select", function (e) {
        //     $(department_name).val([]).trigger("change");
        //     $(department_name).empty();
        //     let item = e.params.data.item.title;

        //     fetch(`${api}?query=${item}`, {
        //         method: "GET",
        //     })
        //         .then((data) => {
        //             return data.json();
        //         })
        //         .then((body) => {
        //             if (body.count != 0) {
        //                 for (let key in body.results) {
        //                     let option_area = document.createElement("option");
        //                     option_area.textContent = body.results[key].title;
        //                     $(department_name)[0].appendChild(option_area);
        //                 }
        //             }
        //         });
        // });
    }

}



export { nova_pochta }
