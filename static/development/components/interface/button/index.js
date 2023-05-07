import './index.scss';
 
$('.btn-lean_more').on('mouseenter', function(){
    $(this).addClass('is-focus-over');
    $(this).removeClass('is-focus-out');
});
$('.btn-lean_more').on('mouseleave', function(){
    $(this).addClass('is-focus-out');
    $(this).removeClass('is-focus-over');

});

    

[...$('.btn-black')].map(item=>{ 
    const current_width = $(item)[0].offsetWidth;
    console.log(current_width);
    $(item).css('width', `${current_width}px`);
});

[...$('.btn-yelow')].map(item=>{ 
    const current_width = $(item)[0].offsetWidth;
    console.log(current_width);
    $(item).css('width', `${current_width}px`);
});

//  $('.burger').on('click',function(){
//      $(this).toggleClass('active')
//  })

