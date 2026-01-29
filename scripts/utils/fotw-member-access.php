<?php
/**
 * Plugin Name: FOTW Member Access
 * Description: Button changes link destination based on WooCommerce Membership plan.
 */

add_filter( 'wp_nav_menu_objects', function ( $items, $args ) {

    // ✅ TARGET BY MENU NAME (Flatsome)
    if ( empty( $args->menu ) ) {
        return $items;
    }

    // $args->menu can be ID, slug, or object
    $menu_name = is_object( $args->menu ) ? $args->menu->name : $args->menu;

    if ( $menu_name !== 'Dashboard' ) {
        return $items;
    }

    if ( ! function_exists( 'wc_memberships_get_user_memberships' ) ) {
        return $items;
    }

    // Collect ACTIVE membership plan slugs
    $active_plans = [];

    foreach ( wc_memberships_get_user_memberships( get_current_user_id() ) as $membership ) {
        if ( $membership->is_active() ) {
            $active_plans[] = $membership->get_plan()->get_slug();
        }
    }

    foreach ( $items as $key => $item ) {

        // Observer
        if (
            in_array( 'requires-observer', $item->classes, true )
            && ! in_array( 'observer-access', $active_plans, true )
        ) {
            unset( $items[ $key ] );
        }

        // Activator
        if (
            in_array( 'requires-activator', $item->classes, true )
            && ! in_array( 'activator-access', $active_plans, true )
        ) {
            unset( $items[ $key ] );
        }

        // Navigator
        if (
            in_array( 'requires-navigator', $item->classes, true )
            && ! in_array( 'navigator-access', $active_plans, true )
        ) {
            unset( $items[ $key ] );
        }

        // Coaching
        if (
            in_array( 'requires-coaching', $item->classes, true )
            && ! in_array( 'coaching-access', $active_plans, true )
        ) {
            unset( $items[ $key ] );
        }
    }

    return $items;

}, 10, 2 );